"""Evaluate frozen next-delivery model candidates and save a reproducible report."""

import hashlib
import json
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.backtesting import evaluate  # noqa: E402
from backend.bayesian import MODEL_VERSION  # noqa: E402
from backend.config import Settings  # noqa: E402
from backend.database import connection  # noqa: E402


def main():
    settings = Settings.from_env()
    started = time.perf_counter()
    with settings.database.open("rb") as handle:
        original_hash = hashlib.file_digest(handle, "sha256").hexdigest()
    print(
        "Reading legal IPL deliveries; validation 2024, untouched holdouts 2025 and 2026.",
        flush=True,
    )
    # Offline archive aggregation has a larger bounded SQL budget than HTTP requests.
    with connection(replace(settings, query_timeout_seconds=30)) as db:
        report = evaluate(db, progress=lambda message: print(message, flush=True))
    with settings.database.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != original_hash:
            raise AssertionError("Database changed during evaluation")
    report.update(
        model_version=MODEL_VERSION,
        database_sha256=original_hash,
        dataset_catalog_sha256=hashlib.sha256(
            (settings.data_dir / "dataset_catalog.json").read_bytes()
        ).hexdigest(),
        completed_at=datetime.now(timezone.utc).isoformat(),
        elapsed_seconds=round(time.perf_counter() - started, 3),
    )
    destination = ROOT / "outputs/bayesian-backtest.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for season, results in report["holdout"].items():
        print(
            f"Holdout {season}: "
            + json.dumps(
                {
                    name: round(score["joint_log_loss"], 6)
                    for name, score in results["metrics"].items()
                }
            ),
            flush=True,
        )
    print(f"Report saved to {destination}", flush=True)


if __name__ == "__main__":
    main()
