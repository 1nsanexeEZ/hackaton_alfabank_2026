"""Обучение ML-модели скоринга: WoE-биннинг + логистическая регрессия.

Запуск из `backend/`:  uv run --group ml python -m ml.train

Что делает:
1. генерирует синтетическую популяцию (`ml.population`): обучающая когорта и когорта «вне
   времени» с более жёсткими условиями кредитования;
2. считает признаки той же функцией, что и прод (`ml_features`);
3. режет признаки на корзины (границы заданы аналитиком — объяснимо), считает WoE по
   обучающей выборке и обучает логистическую регрессию;
4. пишет коэффициенты в `src/modules/scoring/infrastructure/config/ml_logreg_v1.yaml`; границы
   грейдов A–I берёт из PD-модели (`pd_model_v2`), чтобы грейды двух моделей были сравнимы;
5. собирает доменную модель из этого YAML и на ней (ровно как в проде) считает метрики:
   различающая способность (ROC-AUC, Gini, KS), точность (калибровка PD, Brier),
   стабильность (PSI на когорте «вне времени») — для ML-модели, `pd_model_v2` и `scorecard_v1`;
6. пишет отчёт `ml/reports/ml_logreg_v1.md`, графики и фикстуру для теста паритета.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402 — backend Agg выбирается до импорта pyplot
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import yaml  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import brier_score_loss, roc_auc_score, roc_curve  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

from ml.population import DEVELOPMENT, OUT_OF_TIME, Applicant, generate  # noqa: E402
from src.modules.scoring.application.serialization import dump_input  # noqa: E402
from src.modules.scoring.domain.ml_model import (  # noqa: E402
    IndustrySections,
    MlModel,
    ml_features,
)
from src.modules.scoring.infrastructure.config_loader import (  # noqa: E402
    load_pd_model,
    load_scorecard,
)
from src.modules.scoring.infrastructure.ml_loader import load_ml_model_file  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
CONFIG = BACKEND / "src/modules/scoring/infrastructure/config/ml_logreg_v1.yaml"
REPORTS = BACKEND / "ml/reports"
FIXTURE = BACKEND / "tests/scoring/fixtures/ml_parity.json"

VERSION = "ml_logreg_v1"
SEED_DEV, SEED_OOT, SEED_SPLIT = 2026, 2027, 42
N_DEV, N_OOT = 40_000, 15_000

# Границы корзин задаёт аналитик: так корзины читаются человеком, а WoE учится по данным.
NUMERIC: dict[str, tuple[str, list[float]]] = {
    "business_age_months": ("Возраст бизнеса, мес.", [12, 24, 60, 120]),
    "revenue_growth": ("Рост выручки год к году", [-0.2]),
    "debt_service_ratio": ("Платежи по кредитам / месячная выручка", [0.15, 0.3, 0.6]),
    "amount_to_revenue": ("Сумма кредита / годовая выручка", [0.1, 0.3, 0.5]),
    "revenue_gap": ("Расхождение выручки с ФНС", [0.15, 0.3]),
    "bureau_inquiries": ("Запросы в БКИ за 30 дней", [2, 3, 5]),
    "collateral_coverage": ("Покрытие залогом", [1]),
}
CATEGORY: dict[str, str] = {
    "bureau_overdue": "Макс. просрочка за 12 мес.",
    "tax_arrears": "Налоговая недоимка",
    "verification": "Верификация компании",
    "industry_risk": "Отраслевой риск",
    "cash_gap": "Кассовый разрыв по выписке",
    "revenue_confirmed": "Выручка подтверждена выпиской",
}
IV_THRESHOLD = 0.02
GRADES = list("ABCDEFGHIJ")
# Справочник отраслей берём из PD-модели при обучении и записываем в YAML ML-модели: на нём
# посчитаны WoE признака industry_risk, прод читает его оттуда же.
_PD_CONFIG = load_pd_model().config
INDUSTRY = IndustrySections(low=_PD_CONFIG.industry_low, high=_PD_CONFIG.industry_high)
SCALING = {"base_score": 600, "base_odds": 50, "pdo": 40}
MISSING = "__missing__"


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    dev = generate(N_DEV, SEED_DEV, DEVELOPMENT)
    oot = generate(N_OOT, SEED_OOT, OUT_OF_TIME)
    train_idx, test_idx = train_test_split(
        np.arange(len(dev)),
        test_size=0.3,
        random_state=SEED_SPLIT,
        stratify=[a.defaulted for a in dev],
    )
    train = [dev[i] for i in train_idx]
    test = [dev[i] for i in test_idx]

    fitted = fit(train)
    model, woe, selected, iv = fitted.model, fitted.woe, fitted.selected, fitted.iv
    dropped_sign = fitted.dropped_sign

    config = _export(model, woe, selected)
    ml_model = load_ml_model_file(CONFIG)
    pd_model = load_pd_model()
    scorecard = load_scorecard()

    results = {}
    for cohort, rows in (("train", train), ("test", test), ("out_of_time", oot)):
        pred = [ml_model.predict(a.inp) for a in rows]
        base = [pd_model.calculate(a.inp) for a in rows]
        results[cohort] = {
            "y": np.array([a.defaulted for a in rows]),
            "pd": np.array([float(p.pd_12m) for p in pred]),
            "score": np.array([p.score for p in pred]),
            "grade": [p.grade for p in pred],
            "pdm_pd": np.array([float(b.pd_12m) for b in base]),
            "pdm_grade": [b.grade for b in base],
            "sc_score": np.array([scorecard.calculate(a.inp).score for a in rows]),
        }

    # Паритет: доменная модель из YAML против sklearn на тех же данных.
    sk_pd = predict(fitted, test)
    parity = float(np.max(np.abs(sk_pd - results["test"]["pd"])))
    assert parity < 0.005, f"домен и sklearn разошлись на {parity}"

    metrics = _metrics(results)
    config["metadata"]["metrics"] = metrics
    config["metadata"]["parity_max_abs_pd_diff_vs_sklearn"] = round(parity, 6)
    _write_yaml(config)

    _plots(results)
    _report(config, metrics, results, woe, model, iv, selected, dropped_sign)
    _fixture(test[:200], ml_model)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


@dataclass(frozen=True)
class Fitted:
    model: LogisticRegression
    woe: dict[str, dict[str, float]]
    selected: list[str]
    iv: dict[str, float]
    dropped_sign: list[str]


def fit(train: list[Applicant]) -> Fitted:
    """Обучить модель с нуля: WoE → отбор по IV → логрегрессия без неверных знаков."""
    keys_train = _keys(train)
    y_train = np.array([a.defaulted for a in train])
    woe = {name: _woe_table(keys_train[name], y_train) for name in keys_train.columns}
    iv = {name: _information_value(keys_train[name], y_train, woe[name]) for name in woe}
    # Отбор признаков: Information Value < 0,02 — признак почти не различает заёмщиков.
    selected = [name for name in keys_train.columns if iv[name] >= IV_THRESHOLD]
    keys_train = keys_train[selected]
    woe = {name: woe[name] for name in selected}
    # Признак с неверным знаком (рост WoE повышает риск) — обычно дубль другого признака:
    # исключаем по одному и переобучаем, пока все коэффициенты не станут отрицательными.
    dropped_sign: list[str] = []
    while True:
        x_train = _woe_matrix(keys_train, woe)
        model = LogisticRegression(C=1.0, max_iter=2000)
        model.fit(x_train, y_train)
        wrong = [(c, n) for c, n in zip(model.coef_[0], selected, strict=True) if c > 0]
        if not wrong:
            break
        name = max(wrong)[1]
        dropped_sign.append(name)
        selected = [n for n in selected if n != name]
        keys_train = keys_train[selected]
        woe = {n: woe[n] for n in selected}
    return Fitted(model, woe, selected, iv, dropped_sign)


def predict(fitted: Fitted, rows: list[Applicant]) -> np.ndarray:
    """PD по sklearn-модели (для проверок; в проде считает доменная модель из YAML)."""
    keys = _keys(rows)[fitted.selected]
    return fitted.model.predict_proba(_woe_matrix(keys, fitted.woe))[:, 1]


# --- признаки и WoE ---------------------------------------------------------


def _keys(rows: list[Applicant]) -> pd.DataFrame:
    """Ключ корзины для каждого признака: строка с номером корзины или категорией."""
    records = []
    for a in rows:
        values = ml_features(a.inp, INDUSTRY)
        record = {}
        for name, (_, edges) in NUMERIC.items():
            value = values[name]
            record[name] = MISSING if value is None else str(_bin_index(float(value), edges))
        for name in CATEGORY:
            value = values[name]
            record[name] = MISSING if value is None else str(value)
        records.append(record)
    return pd.DataFrame.from_records(records)


def _bin_index(value: float, edges: list[float]) -> int:
    for i, edge in enumerate(edges):
        if value < edge:
            return i
    return len(edges)


def _woe_table(keys: pd.Series, y: np.ndarray) -> dict[str, float]:
    frame = pd.DataFrame({"key": keys.to_numpy(), "bad": y})
    stats = frame.groupby("key")["bad"].agg(["sum", "count"])
    bad_total, good_total, k = stats["sum"].sum(), (stats["count"] - stats["sum"]).sum(), len(stats)
    table = {}
    for key, row in stats.iterrows():
        bad, good = row["sum"], row["count"] - row["sum"]
        table[str(key)] = math.log(
            ((good + 0.5) / (good_total + 0.5 * k)) / ((bad + 0.5) / (bad_total + 0.5 * k))
        )
    return table


def _information_value(keys: pd.Series, y: np.ndarray, table: dict[str, float]) -> float:
    frame = pd.DataFrame({"key": keys.to_numpy(), "bad": y})
    stats = frame.groupby("key")["bad"].agg(["sum", "count"])
    bad_total, good_total = stats["sum"].sum(), (stats["count"] - stats["sum"]).sum()
    total = 0.0
    for key, row in stats.iterrows():
        good_share = (row["count"] - row["sum"]) / good_total
        bad_share = row["sum"] / bad_total
        total += (good_share - bad_share) * table[str(key)]
    return float(total)


def _in_model(name: str, selected: list[str], dropped_sign: list[str]) -> str:
    if name in selected:
        return "да"
    return "нет — неверный знак" if name in dropped_sign else "нет — IV"


def _monotonic(name: str, table: dict[str, float]) -> str:
    if name not in NUMERIC:
        return "—"
    values = [table[str(i)] for i in range(len(NUMERIC[name][1]) + 1) if str(i) in table]
    steps = [b - a for a, b in zip(values, values[1:], strict=False)]
    if all(step >= 0 for step in steps) or all(step <= 0 for step in steps):
        return "да"
    return "нет"


def _woe_matrix(keys: pd.DataFrame, woe: dict[str, dict[str, float]]) -> np.ndarray:
    columns = [keys[name].map(lambda k, n=name: woe[n].get(k, 0.0)) for name in keys.columns]
    return np.column_stack(columns)


# --- экспорт ----------------------------------------------------------------


def _export(model: LogisticRegression, woe: dict[str, dict[str, float]], names: list[str]) -> dict:
    coefs = dict(zip(names, model.coef_[0], strict=True))
    features: list[dict[str, Any]] = []
    for name in names:
        table = woe[name]
        missing = _dec(table.get(MISSING, 0.0))
        if name in NUMERIC:
            title, edges = NUMERIC[name]
            bins = []
            for i in range(len(edges) + 1):
                upper = None if i == len(edges) else _num(edges[i])
                bins.append(
                    {"upper": upper, "woe": _dec(table.get(str(i), 0.0)), "label": _label(i, edges)}
                )
            features.append(
                {
                    "name": name,
                    "title": title,
                    "kind": "numeric",
                    "coef": _dec(coefs[name]),
                    "missing_woe": missing,
                    "bins": bins,
                }
            )
        else:
            categories = {k: _dec(v) for k, v in sorted(table.items()) if k != MISSING}
            features.append(
                {
                    "name": name,
                    "title": CATEGORY[name],
                    "kind": "category",
                    "coef": _dec(coefs[name]),
                    "missing_woe": missing,
                    "categories": categories,
                }
            )
    config = {
        "version": VERSION,
        "intercept": _dec(model.intercept_[0]),
        "scaling": {k: str(v) for k, v in SCALING.items()},
        "grade_bands": [{"grade": g, "max_pd": str(p)} for g, p in load_pd_model().config.grades],
        "industry_sections": {"low": sorted(INDUSTRY.low), "high": sorted(INDUSTRY.high)},
        "features": features,
        "metadata": {
            "method": "WoE-биннинг + логистическая регрессия (L2, C=1.0)",
            "data": "синтетика: ml/population.py, дефолт — отдельный «истинный» процесс",
            "seeds": {"development": SEED_DEV, "out_of_time": SEED_OOT, "split": SEED_SPLIT},
            "sizes": {"development": N_DEV, "out_of_time": N_OOT, "test_share": 0.3},
        },
    }
    _write_yaml(config)
    return config


def _write_yaml(config: dict) -> None:
    header = (
        "# ML-модель скоринга — генерируется `uv run --group ml python -m ml.train`,\n"
        "# руками не править: метрики и паритет с обучением — в metadata и ml/reports.\n"
    )
    CONFIG.write_text(
        header + yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )


def _label(i: int, edges: list[float]) -> str:
    if i == 0:
        return f"<{_num(edges[0])}"
    if i == len(edges):
        return f"≥{_num(edges[-1])}"
    return f"{_num(edges[i - 1])}–{_num(edges[i])}"


def _num(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def _dec(value: float) -> str:
    return str(Decimal(str(float(value))).quantize(Decimal("0.000001")))


# --- метрики ----------------------------------------------------------------


def _metrics(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for cohort in ("test", "out_of_time"):
        r = results[cohort]
        out[cohort] = {
            "default_rate": round(float(r["y"].mean()), 4),
            "ml": _discrimination(r["y"], r["pd"]),
            "pd_model_v2": _discrimination(r["y"], r["pdm_pd"]),
            "scorecard_v1": _discrimination(r["y"], -r["sc_score"]),
        }
        for name, key in (("ml", "pd"), ("pd_model_v2", "pdm_pd")):
            out[cohort][name]["brier"] = round(float(brier_score_loss(r["y"], r[key])), 4)
            out[cohort][name]["mean_pd"] = round(float(r[key].mean()), 4)
    # Скор PD-модели сравним только внутри сегмента, поэтому её стабильность — по PD.
    out["stability_psi_train_vs_out_of_time"] = {
        "ml": round(_psi(results["train"]["pd"], results["out_of_time"]["pd"]), 4),
        "pd_model_v2": round(_psi(results["train"]["pdm_pd"], results["out_of_time"]["pdm_pd"]), 4),
    }
    return out


def _discrimination(y: np.ndarray, risk: np.ndarray) -> dict[str, float]:
    auc = float(roc_auc_score(y, risk))
    fpr, tpr, _ = roc_curve(y, risk)
    return {
        "roc_auc": round(auc, 4),
        "gini": round(2 * auc - 1, 4),
        "ks": round(float(np.max(tpr - fpr)), 4),
    }


def _psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, buckets + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    e = np.histogram(expected, edges)[0] / len(expected)
    a = np.histogram(actual, edges)[0] / len(actual)
    e, a = np.clip(e, 1e-6, None), np.clip(a, 1e-6, None)
    return float(np.sum((a - e) * np.log(a / e)))


# --- графики, отчёт, фикстура ----------------------------------------------


def _plots(results: dict[str, dict[str, Any]]) -> None:
    test = results["test"]
    fig, ax = plt.subplots(figsize=(5.5, 5))
    for label, risk in (
        (VERSION, test["pd"]),
        ("pd_model_v2", test["pdm_pd"]),
        ("scorecard_v1", -test["sc_score"]),
    ):
        fpr, tpr, _ = roc_curve(test["y"], risk)
        ax.plot(fpr, tpr, label=f"{label} (AUC {roc_auc_score(test['y'], risk):.3f})")
    ax.plot([0, 1], [0, 1], "--", color="grey", linewidth=1)
    ax.set(
        xlabel="Доля хороших, отказанных зря", ylabel="Доля пойманных дефолтов", title="ROC, тест"
    )
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(REPORTS / "roc.png", dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.5, 5))
    top = 0.0
    for label, key in ((VERSION, "pd"), ("pd_model_v2", "pdm_pd")):
        frame = pd.DataFrame({"pd": test[key], "y": test["y"]})
        frame["decile"] = pd.qcut(frame["pd"], 10, labels=False, duplicates="drop")
        calib = frame.groupby("decile").agg(predicted=("pd", "mean"), observed=("y", "mean"))
        ax.plot(calib["predicted"], calib["observed"], "o-", label=f"{label}, децили PD")
        top = max(top, float(calib["predicted"].max()), float(calib["observed"].max()))
    top *= 1.05
    ax.plot([0, top], [0, top], "--", color="grey", linewidth=1, label="идеальная калибровка")
    ax.set(xlabel="Предсказанный PD", ylabel="Фактическая доля дефолтов", title="Калибровка, тест")
    ax.legend()
    fig.tight_layout()
    fig.savefig(REPORTS / "calibration.png", dpi=120)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True)
    for ax, (label, grades) in zip(
        axes, ((VERSION, test["grade"]), ("pd_model_v2", test["pdm_grade"])), strict=True
    ):
        table = pd.DataFrame({"grade": grades, "y": test["y"]}).groupby("grade")["y"].mean()
        table = table.reindex(GRADES).fillna(0)
        ax.bar(table.index, table.values)
        ax.set(title=label, xlabel="Грейд", ylabel="Доля дефолтов")
    fig.tight_layout()
    fig.savefig(REPORTS / "grades.png", dpi=120)
    plt.close(fig)


def _model_row(name: str, test: dict[str, float], oot: dict[str, float]) -> str:
    cells = [test["roc_auc"], test["gini"], test["ks"], oot["roc_auc"], oot["gini"]]
    return f"| {name} | " + " | ".join(str(c) for c in cells) + " |"


def _calibration_row(name: str, test: dict[str, float], oot: dict[str, float]) -> str:
    return (
        f"| {name} | {test['mean_pd']:.1%} | {test['brier']} | {oot['mean_pd']:.1%} | "
        f"{oot['brier']} |"
    )


def _grade_table(grades: list[str], y: np.ndarray) -> str:
    frame = pd.DataFrame({"grade": grades, "y": y})
    rows = ["| Грейд | Заявок | Доля | Дефолтов |", "|---|---|---|---|"]
    for grade in GRADES:
        part = frame[frame["grade"] == grade]
        share = len(part) / len(frame)
        rate = f"{part['y'].mean():.1%}" if len(part) else "—"
        rows.append(f"| {grade} | {len(part)} | {share:.1%} | {rate} |")
    return "\n".join(rows)


def _zone(grade: str) -> str:
    return "green" if grade in "ABCD" else "yellow" if grade in "EFG" else "red"


def _zone_table(results: dict[str, Any]) -> str:
    """Матрица зон двух моделей на тесте: сколько заявок и сколько из них дефолтов."""
    frame = pd.DataFrame(
        {
            "pdm": [_zone(g) for g in results["pdm_grade"]],
            "ml": [_zone(g) for g in results["grade"]],
            "y": results["y"],
        }
    )
    zones = ("green", "yellow", "red")
    rows = ["| PD-модель ↓ / ML → | green | yellow | red |", "|---|---|---|---|"]
    for pdm in zones:
        cells = []
        for ml in zones:
            part = frame[(frame["pdm"] == pdm) & (frame["ml"] == ml)]
            rate = f"{part['y'].mean():.1%}" if len(part) else "—"
            cells.append(f"{len(part)} ({rate})")
        rows.append(f"| {pdm} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def _report(
    config: dict,
    metrics: dict[str, Any],
    results: dict[str, dict[str, Any]],
    woe: dict[str, dict[str, float]],
    model: LogisticRegression,
    iv: dict[str, float],
    selected: list[str],
    dropped_sign: list[str],
) -> None:
    t, o = metrics["test"], metrics["out_of_time"]
    psi = metrics["stability_psi_train_vs_out_of_time"]
    coef_rows = ["| Признак | Коэффициент |", "|---|---|"] + [
        f"| {f['title']} (`{f['name']}`) | {float(f['coef']):.3f} |" for f in config["features"]
    ]
    titles = {**{k: v[0] for k, v in NUMERIC.items()}, **CATEGORY}
    iv_rows = ["| Признак | IV | В модели | WoE монотонен |", "|---|---|---|---|"] + [
        f"| {titles[name]} (`{name}`) | {value:.3f} | {_in_model(name, selected, dropped_sign)} | "
        f"{_monotonic(name, woe[name]) if name in woe else '—'} |"
        for name, value in sorted(iv.items(), key=lambda kv: -kv[1])
    ]
    bands = ", ".join(f"{b['grade']} < {float(b['max_pd']):.2%}" for b in config["grade_bands"])
    text = f"""# {VERSION} — отчёт об обучении

Сгенерирован `uv run --group ml python -m ml.train`. Данные синтетические (`ml/population.py`):
дефолт задаётся отдельным «истинным» процессом (покрытие платежа денежным потоком, просрочки,
падение выручки, завышение выручки в анкете, шум), а не баллами какой-либо из моделей. Метрики
посчитаны доменной моделью, собранной из экспортированного YAML, — ровно тем кодом, что работает
в проде. Для сравнения — экспертная PD-модель `pd_model_v2` и старая скоркарта `scorecard_v1`.

## Данные

| Когорта | Заявок | Доля дефолтов |
|---|---|---|
| Обучение + тест (70/30) | {N_DEV} | {results["train"]["y"].mean():.1%} / {t["default_rate"]:.1%} |
| Вне времени (стресс: рост выручки −8 п.п., ставки +4 п.п.) | {N_OOT} | {o["default_rate"]:.1%} |

## Различающая способность

| Модель | ROC-AUC тест | Gini тест | KS тест | ROC-AUC вне времени | Gini вне времени |
|---|---|---|---|---|---|
{_model_row(VERSION, t["ml"], o["ml"])}
{_model_row("pd_model_v2", t["pd_model_v2"], o["pd_model_v2"])}
{_model_row("scorecard_v1", t["scorecard_v1"], o["scorecard_v1"])}

![ROC](roc.png)

## Точность (калибровка PD)

Фактическая доля дефолтов: тест {t["default_rate"]:.1%}, вне времени {o["default_rate"]:.1%}.

| Модель | Средний PD, тест | Brier, тест | Средний PD, вне времени | Brier, вне времени |
|---|---|---|---|---|
{_calibration_row(VERSION, t["ml"], o["ml"])}
{_calibration_row("pd_model_v2", t["pd_model_v2"], o["pd_model_v2"])}

ML-модель обучена на исходах, поэтому её PD откалиброван по данным; калибровку PD-модели задал
эксперт. В стрессе («вне времени») обе модели недооценивают риск — аргумент за регулярный
пересмотр.

![Калибровка](calibration.png)

## Стабильность

PSI распределения PD, обучение → «вне времени»: ML {psi["ml"]}, pd_model_v2
{psi["pd_model_v2"]} (< 0,1 — стабильно, 0,1–0,25 — заметный сдвиг, > 0,25 — пересмотр).

## Грейды на тесте

Шкала грейдов общая с PD-моделью ({bands}, выше — J), поэтому грейды двух моделей сравнимы
напрямую.

{VERSION}:

{_grade_table(results["test"]["grade"], results["test"]["y"])}

pd_model_v2:

{_grade_table(results["test"]["pdm_grade"], results["test"]["y"])}

![Грейды](grades.png)

## Две модели вместе (зоны для `policy_v5`)

Зоны: green — A–D, yellow — E–G, red — H–J. В ячейке — заявок на тесте и доля дефолтов среди них.

{_zone_table(results["test"])}

## Отбор признаков

Information Value по обучающей выборке; признаки с IV < {IV_THRESHOLD} не берём (почти не различают
заёмщиков). Шкала: < 0,02 — бесполезен, 0,02–0,1 — слабый, 0,1–0,3 — средний, > 0,3 — сильный.

{chr(10).join(iv_rows)}

Признак с положительным коэффициентом (рост WoE повышает риск) исключается и модель
переобучается: обычно это дубль другого признака, и в модели он только путает объяснение.

## Коэффициенты

Коэффициент отрицательный — признак работает «как ожидалось» (чем выше WoE, тем ниже риск).

{chr(10).join(coef_rows)}

Свободный член {float(model.intercept_[0]):.3f}. Корзины и WoE — в
`src/modules/scoring/infrastructure/config/{VERSION}.yaml`.

## Паритет

Максимальная разница PD доменной модели и sklearn на тесте:
{config["metadata"]["parity_max_abs_pd_diff_vs_sklearn"]} (коэффициенты округлены до 6 знаков).

## Ограничения

- Данные синтетические: метрики показывают, что конвейер обучения, валидации и инференса
  работает, а не реальное качество на клиентах банка. В проде модель переобучается на истории.
- Границы корзин заданы вручную ради читаемости; на реальных данных — подбор с монотонностью WoE.
"""
    (REPORTS / f"{VERSION}.md").write_text(text, encoding="utf-8")


def _fixture(rows: list[Applicant], ml_model: MlModel) -> None:
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for a in rows:
        result = ml_model.predict(a.inp)
        records.append(
            {
                "input": dump_input(a.inp),
                "pd_12m": str(result.pd_12m),
                "score": result.score,
                "grade": result.grade,
                "reason_codes": list(result.reason_codes),
            }
        )
    FIXTURE.write_text(
        json.dumps({"model": VERSION, "rows": records}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
