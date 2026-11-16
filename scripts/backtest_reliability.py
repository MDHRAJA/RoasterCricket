"""Measure genuine pre-match benchmarks; never label this simulator calibration."""

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import Settings  # noqa: E402
from backend.database import connection  # noqa: E402
from backend.reliability import BENCHMARK_VERSION, archive  # noqa: E402
from backend.reliability_backtesting import evaluate  # noqa: E402


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    settings = Settings.from_env()
    original_hash = digest(settings.database)
    started = time.monotonic()
    with connection(settings) as db:
        rows = archive(db)
        total = db.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    print(f"Read {len(rows)} eligible first-innings records; tuning 2024 only.", flush=True)
    report = evaluate(rows)
    assert original_hash == digest(settings.database), "Database was mutated"
    report.update(
        model_version=BENCHMARK_VERSION,
        database_sha256=original_hash,
        dataset_catalog_sha256=digest(settings.data_dir / "dataset_catalog.json"),
        eligible_first_innings=len(rows),
        matches_excluded_by_format_screen=total - len(rows),
        completed_at=datetime.now(timezone.utc).isoformat(),
        elapsed_seconds=round(time.monotonic() - started, 3),
    )
    (ROOT / "outputs/reliability-backtest.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print("Selected from validation:", report["selected_configuration"], flush=True)
    for season, result in report["holdout"].items():
        print(
            season,
            json.dumps({"wins": result["win_metrics"], "scores": result["score_metrics"]}),
            flush=True,
        )


if __name__ == "__main__":
    main()
