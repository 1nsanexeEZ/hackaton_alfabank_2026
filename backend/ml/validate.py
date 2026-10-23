"""Проверки честности ML-модели — насколько можно доверять сравнению с PD-моделью.

Запуск из `backend/`:  uv run --group ml python -m ml.validate

1. **Значимость.** Бутстрап (1000 перевыборок тестовой когорты): доверительные интервалы Gini
   ML-модели, PD-модели (`pd_model_v2`) и их разницы. Если интервал разницы не задевает ноль —
   преимущество не случайность выборки.
2. **Устойчивость к допущениям.** Данные синтетические, а их параметры (доля завышающих выручку,
   маржа, шум, сила влияния денежного потока) выбрали мы. Меняем каждый параметр, переобучаем
   ML-модель с нуля и смотрим, сохраняется ли преимущество.
3. **Честность сравнения.** Генерируем данные, где «правда» — сама PD-модель. Тогда она —
   идеальная модель, и ML-модель не должна её обыгрывать. Если обыгрывает — сравнение
   перекошено в его пользу.

Пишет `ml/reports/ml_validation.md`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split

from ml.population import BASELINE, DEVELOPMENT, OUT_OF_TIME, Applicant, Assumptions, generate
from ml.train import N_DEV, N_OOT, SEED_DEV, SEED_OOT, SEED_SPLIT, fit, predict
from src.modules.scoring.infrastructure.config_loader import load_pd_model
from src.modules.scoring.infrastructure.ml_loader import load_ml_model

REPORT = Path(__file__).resolve().parent / "reports" / "ml_validation.md"
N_BOOT, N_BOOT_VARIANT, SEED_BOOT = 1000, 300, 7
N_VARIANT = 30_000

_PD_MODEL = load_pd_model()

VARIANTS: list[tuple[str, str, Assumptions]] = [
    ("baseline", "базовые допущения (как при обучении)", BASELINE),
    ("noise_x2", "вдвое больше случайности в дефолтах", replace(BASELINE, noise=1.0)),
    ("noise_half", "вдвое меньше случайности", replace(BASELINE, noise=0.25)),
    ("no_fraud", "никто не завышает выручку", replace(BASELINE, fraud_share=0.0)),
    ("fraud_x2", "выручку завышает каждый четвёртый", replace(BASELINE, fraud_share=0.25)),
    ("thin_margin", "маржа ниже: 12% вместо 18%", replace(BASELINE, margin_mean=0.12)),
    (
        "weak_cashflow",
        "денежный поток влияет на дефолт втрое слабее",
        replace(BASELINE, coverage_weight=0.55),
    ),
]


@dataclass(frozen=True)
class Interval:
    mean: float
    low: float
    high: float

    def text(self) -> str:
        return f"{self.mean:.3f} [{self.low:.3f}; {self.high:.3f}]"


def main() -> None:
    significance = _significance()
    sensitivity = [_variant(name, title, a) for name, title, a in VARIANTS]
    fairness = _fairness()
    _report(significance, sensitivity, fairness)
    print(
        json.dumps(
            {
                "significance": {k: v["diff"].text() for k, v in significance.items()},
                "sensitivity": {s["name"]: s["diff"].text() for s in sensitivity},
                "fairness": {
                    k: v if isinstance(v, float) else v.text() for k, v in fairness.items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


# --- 1. значимость ----------------------------------------------------------


def _significance() -> dict[str, dict[str, Interval]]:
    """Боевая модель из YAML на той же тестовой когорте и когорте «вне времени», что в отчёте."""
    ml_model = load_ml_model()
    dev = generate(N_DEV, SEED_DEV, DEVELOPMENT)
    _, test = _split(dev)
    oot = generate(N_OOT, SEED_OOT, OUT_OF_TIME)
    out = {}
    for cohort, rows in (("test", test), ("out_of_time", oot)):
        y = _y(rows)
        ml = np.array([float(ml_model.predict(a.inp).pd_12m) for a in rows])
        out[cohort] = _bootstrap(y, ml, _pd_model_risk(rows), N_BOOT)
    return out


def _bootstrap(y: np.ndarray, ml: np.ndarray, pdm: np.ndarray, n: int) -> dict[str, Interval]:
    rng = np.random.default_rng(SEED_BOOT)
    g_ml, g_pdm, diff = [], [], []
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].min() == y[idx].max():
            continue
        a, b = _gini(y[idx], ml[idx]), _gini(y[idx], pdm[idx])
        g_ml.append(a)
        g_pdm.append(b)
        diff.append(a - b)
    return {"ml": _interval(g_ml), "pd_model": _interval(g_pdm), "diff": _interval(diff)}


# --- 2. устойчивость к допущениям ------------------------------------------


def _variant(name: str, title: str, assumptions: Assumptions) -> dict:
    rows = generate(N_VARIANT, SEED_DEV, DEVELOPMENT, assumptions)
    train, test = _split(rows)
    fitted = fit(train)
    y = _y(test)
    boot = _bootstrap(y, predict(fitted, test), _pd_model_risk(test), N_BOOT_VARIANT)
    return {
        "name": name,
        "title": title,
        "default_rate": float(_y(rows).mean()),
        "ml": boot["ml"],
        "pd_model": boot["pd_model"],
        "diff": boot["diff"],
        "features": len(fitted.selected),
    }


# --- 3. честность сравнения -------------------------------------------------


def _fairness() -> dict:
    """«Правда» = PD-модель: дефолт ~ Bernoulli(PD модели, сдвинутый по логиту до доли 7%)."""
    rows = generate(N_VARIANT, SEED_DEV, DEVELOPMENT)
    pds = _pd_model_pd(rows)
    logits = np.log(pds / (1 - pds))
    shift = _shift_for_rate(logits, target=0.07)
    true_pd = 1 / (1 + np.exp(-(logits + shift)))
    rng = np.random.default_rng(SEED_BOOT)
    relabelled = [
        Applicant(inp=a.inp, defaulted=int(rng.random() < p), true_pd=float(p))
        for a, p in zip(rows, true_pd, strict=True)
    ]
    train, test = _split(relabelled)
    fitted = fit(train)
    y = _y(test)
    boot = _bootstrap(y, predict(fitted, test), _pd_model_risk(test), N_BOOT_VARIANT)
    oracle = _gini(y, np.array([a.true_pd for a in test]))
    return {
        "default_rate": float(_y(relabelled).mean()),
        "oracle_gini": oracle,
        "ml": boot["ml"],
        "pd_model": boot["pd_model"],
        "diff": boot["diff"],
    }


def _shift_for_rate(logits: np.ndarray, target: float) -> float:
    low, high = -10.0, 10.0
    for _ in range(60):
        mid = (low + high) / 2
        rate = float(np.mean(1 / (1 + np.exp(-(logits + mid)))))
        low, high = (mid, high) if rate < target else (low, mid)
    return (low + high) / 2


# --- общее -----------------------------------------------------------------


def _split(rows: list[Applicant]) -> tuple[list[Applicant], list[Applicant]]:
    train_idx, test_idx = train_test_split(
        np.arange(len(rows)), test_size=0.3, random_state=SEED_SPLIT, stratify=_y(rows)
    )
    return [rows[i] for i in train_idx], [rows[i] for i in test_idx]


def _y(rows: list[Applicant]) -> np.ndarray:
    return np.array([a.defaulted for a in rows])


def _pd_model_pd(rows: list[Applicant]) -> np.ndarray:
    # PD с шагом 0,0001 бывает 0 у лучших заявок — прижимаем, чтобы логит был конечным.
    pds = np.array([float(_PD_MODEL.calculate(a.inp).pd_12m) for a in rows])
    return np.clip(pds, 1e-4, 1 - 1e-4)


def _pd_model_risk(rows: list[Applicant]) -> np.ndarray:
    return _pd_model_pd(rows)


def _gini(y: np.ndarray, risk: np.ndarray) -> float:
    return 2 * float(roc_auc_score(y, risk)) - 1


def _interval(values: list[float]) -> Interval:
    arr = np.array(values)
    return Interval(
        float(arr.mean()), float(np.quantile(arr, 0.025)), float(np.quantile(arr, 0.975))
    )


def _verdict(diff: Interval) -> str:
    if diff.low > 0:
        return "ML лучше"
    if diff.high < 0:
        return "PD-модель лучше"
    return "разница не значима"


def _report(significance: dict, sensitivity: list[dict], fairness: dict) -> None:
    sig_rows = [
        f"| {cohort} | {v['ml'].text()} | {v['pd_model'].text()} | {v['diff'].text()} | "
        f"{_verdict(v['diff'])} |"
        for cohort, v in (
            ("тест", significance["test"]),
            ("вне времени", significance["out_of_time"]),
        )
    ]
    sens_rows = [
        f"| {s['title']} | {s['default_rate']:.1%} | {s['features']} | {s['ml'].text()} | "
        f"{s['pd_model'].text()} | {s['diff'].text()} | {_verdict(s['diff'])} |"
        for s in sensitivity
    ]
    wins = sum(1 for s in sensitivity if s["diff"].low > 0)
    fair_diff = fairness["diff"]
    fair_ok = fair_diff.high <= 0.02  # ML не обыгрывает «правду» заметнее шума
    fair_verdict = (
        "сравнение честное: ML-модель не обыгрывает PD-модель, когда правда — PD-модель"
        if fair_ok
        else "ВНИМАНИЕ: ML-модель обыгрывает PD-модель даже там, где она — правда; "
        "сравнение перекошено"
    )
    text = f"""# ml_logreg_v1 — проверки честности

Сгенерирован `uv run --group ml python -m ml.validate`. В скобках — 95% доверительный интервал по
бутстрапу. Gini — различающая способность (0 — угадывание, 1 — идеально). Сравнение — с
экспертной PD-моделью `pd_model_v2`, которая работает рядом с ML-моделью.

## 1. Значимость разницы (боевая модель из YAML, {N_BOOT} перевыборок)

| Когорта | Gini ML | Gini pd_model_v2 | Разница | Вывод |
|---|---|---|---|---|
{chr(10).join(sig_rows)}

## 2. Устойчивость к нашим допущениям о данных

Для каждого варианта — новая популяция ({N_VARIANT} заявок), ML-модель обучается с нуля по той же
процедуре (WoE, отбор по IV, исключение неверных знаков); бутстрап {N_BOOT_VARIANT} перевыборок.

| Вариант данных | Доля дефолтов | Признаков | Gini ML | Gini pd_model_v2 | Разница | Вывод |
|---|---|---|---|---|---|---|
{chr(10).join(sens_rows)}

ML-модель значимо лучше в {wins} из {len(sensitivity)} вариантов.

## 3. Честность сравнения: «правда» — сама PD-модель

Дефолт сгенерирован прямо из PD `pd_model_v2` (логит сдвинут до доли дефолтов
{fairness["default_rate"]:.1%}). PD-модель здесь — идеальная модель: её Gini совпадает с потолком
(Gini истинной вероятности {fairness["oracle_gini"]:.3f}).

| Модель | Gini |
|---|---|
| pd_model_v2 (правда) | {fairness["pd_model"].text()} |
| ML, обученная на этих данных | {fairness["ml"].text()} |
| разница | {fair_diff.text()} |

Итог: {fair_verdict}.

## Как читать

- Разница на синтетике — свойство **наших допущений о данных**, а не доказательство качества на
  клиентах банка; проверки выше показывают, насколько она устойчива к этим допущениям и не
  создана ли самой процедурой сравнения.
- Поэтому модели работают вместе, а не одна вместо другой: решение видит обе оценки
  (`policy_v5`), расхождение уходит андеррайтеру.
- Реальное качество покажет только обучение и валидация на истории банка.
"""
    REPORT.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
