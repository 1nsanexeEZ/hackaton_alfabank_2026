"""Run the question set against a live model and print the metrics for docs/ai.md.

    ASSISTANT_LLM_PROVIDER=local ASSISTANT_LLM_BASE_URL=http://localhost:11434/v1 \
        uv run python -m tests.assistant.evaluate [--runs 1] [--out result.json]

The backend runs in process on SQLite with the S-1…S-8 fixtures; the model is the
one `ASSISTANT_LLM_*` points at (`local` or `api`).

Metrics:
- passed      share of model answers shown after the post-check (of those sent to the model);
- fallbacks   why the template was used instead (postcheck, timeout, unavailable, busy);
- intent      share of questions routed as expected;
- expected    share of answers that contain the expected fragments (any mode);
- leaks       model answers shown with internal terms (must be 0: the post-check stops them);
- latency     p50 / p95 of the whole answer, seconds, for questions sent to the model.
"""

import argparse
import json
import statistics
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from src.core.config import Settings
from src.main import create_app
from src.modules.assistant.domain.postcheck import INTERNAL_TERMS
from src.modules.assistant.infrastructure.adapters.rate_limiter import InMemoryRateLimiter
from tests.assistant.chat import Chat, use_fixtures
from tests.helpers import create_schema

QUESTIONS: list[dict[str, Any]] = json.loads(
    (Path(__file__).parent / "data" / "questions.json").read_text(encoding="utf-8")
)


def run(runs: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
            database_url=f"sqlite+aiosqlite:///{(Path(tmp) / 'eval.db').as_posix()}",
            jwt_private_key_path=Path(tmp) / "keys" / "private.pem",
            jwt_public_key_path=Path(tmp) / "keys" / "public.pem",
            messaging_mode="manual",
            minio_ensure_bucket=False,
            run_background_jobs=False,
        )
        create_schema(settings.database_url)
        # The model comes from the env (ASSISTANT_LLM_*), as on the stand.
        app = create_app(settings)
        if app.state.assistant_model.model is None:
            sys.exit(f"no model: {app.state.assistant_model.disabled_reason}")
        app.state.assistant_rate_limiter = InMemoryRateLimiter(10_000, 60.0, time.monotonic)
        source = use_fixtures(app)
        # One event loop for every request: the model client keeps its connections in it.
        with TestClient(app) as client:
            status = client.get("/assistant/status").json()
            if status["mode"] != "llm":
                sys.exit(f"model is not reachable: {status}")
            rows = _ask_all(Chat(client, source), runs)

    sent = [r for r in rows if r["sent_to_model"]]
    latencies = sorted(r["seconds"] for r in sent) or [0.0]
    return {
        "provider": status["provider"],
        "model": status["model"],
        "questions": len(QUESTIONS),
        "runs": runs,
        "sent_to_model": len(sent),
        "passed": round(sum(r["mode"] == "llm" for r in sent) / max(1, len(sent)), 3),
        "fallbacks": dict(Counter(r["fallback"] for r in sent if r["fallback"])),
        "intent": round(sum(r["intent_ok"] for r in rows) / len(rows), 3),
        "expected": round(sum(r["expected_ok"] for r in rows) / len(rows), 3),
        "leaks": sum(r["leak"] for r in rows),
        "latency_p50_s": round(statistics.median(latencies), 2),
        "latency_p95_s": round(latencies[max(0, int(len(latencies) * 0.95) - 1)], 2),
        "rows": rows,
    }


def _ask_all(chat: Chat, runs: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _ in range(runs):
        for q in QUESTIONS:
            started = time.perf_counter()
            answer = chat.ask(q["user"], q["text"], q["scenario"]).json()
            elapsed = time.perf_counter() - started
            text = answer["text"]
            rows.append(
                {
                    "id": q["id"],
                    "intent_ok": answer["intent"] == q["intent"],
                    "expected_ok": all(f.lower() in text.lower() for f in q["contains"]),
                    "mode": answer["mode"],
                    "fallback": answer["fallback_reason"],
                    "sent_to_model": answer["fallback_reason"] not in ("template_only", "disabled"),
                    "leak": answer["mode"] == "llm"
                    and any(p.search(text) for _, p in INTERNAL_TERMS),
                    "seconds": round(elapsed, 2),
                    "text": text,
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = run(args.runs)
    if args.out:
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {k: v for k, v in result.items() if k != "rows"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
