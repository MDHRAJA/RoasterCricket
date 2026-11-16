"""Audit completed match forecasts against source data, cutoffs and fitted metrics."""

import hashlib
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import Settings  # noqa: E402
from backend.database import connection  # noqa: E402
from backend.historical_planning import PriorStrategies, historical_cases  # noqa: E402
from backend.match_backtesting import summarize  # noqa: E402


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main():
    settings = Settings.from_env()
    report_path = ROOT / "outputs/full-match-backtest.json"
    report = json.loads(report_path.read_text("utf-8"))
    checks = []

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    check(
        "Complete report, not checkpoint or smoke test",
        report["complete_requested_cohort"] is True
        and report["status"] == "completed_retrospective_diagnostic_not_prospective_validation",
    )
    signature = report["signature"]
    check(
        "Database digest matches evaluated data",
        digest(settings.database) == signature["database_sha256"],
    )
    check(
        "Catalog digest matches evaluated data",
        digest(settings.data_dir / "dataset_catalog.json") == signature["dataset_catalog_sha256"],
    )
    for relative, expected in signature["source_sha256"].items():
        check(f"Source fingerprint: {relative}", digest(ROOT / relative) == expected)
    with connection(Settings(settings.data_dir, query_timeout_seconds=30)) as db:
        all_cases, all_excluded = historical_cases(db, range(2008, 2027))
        cases = {c["match_id"]: c for c in all_cases if c["season"] in (2024, 2025, 2026)}
        strategies = PriorStrategies.from_database(db)
        totals = {
            int(r[0]): int(r[1])
            for r in db.execute(
                "SELECT season,COUNT(*) FROM matches WHERE CAST(season AS INT) BETWEEN 2024 AND 2026 GROUP BY season"
            )
        }
    exclusions = [c for c in all_excluded if c["season"] in (2024, 2025, 2026)]
    check(
        "All format exclusions are attributable", report["format_result_exclusions"] == exclusions
    )
    for season, total in totals.items():
        check(
            f"Every {season} source match accounted for",
            sum(c["season"] == season for c in cases.values())
            + sum(c["season"] == season for c in exclusions)
            == total,
        )
    records = report["predictions"]
    check(
        "No duplicate variant/match forecasts",
        len({(r["variant"], r["match_id"]) for r in records}) == len(records),
    )
    for variant in ("population", "participant_raw", "participant_delivery_corrected"):
        expected = {
            mid
            for mid, c in cases.items()
            if variant == "population"
            or (
                c["participant_conditioned_supported"]
                and (variant != "participant_delivery_corrected" or c["season"] >= 2025)
            )
        }
        actual = {r["match_id"] for r in records if r["variant"] == variant}
        check(f"Complete eligible cohort: {variant}", actual == expected)
    for r in records:
        c = cases[r["match_id"]]
        check(
            f"Cutoff and outcome: {r['variant']} {r['match_id']}",
            r["window_start"] <= r["latest_training_date"] < r["date"]
            and r["outcome"] == int(c["actual"]["winner_id"] == c["team_a_id"]),
        )
        check(
            f"Monte Carlo estimator: {r['variant']} {r['match_id']}",
            0 < r["probability"] < 1
            and r["probability"] == (r["winning_trials"] + 0.5) / (r["decisive_trials"] + 1)
            and 0 < r["decisive_trials"] <= signature["simulations"],
        )
        check(
            f"Actual scores: {r['variant']} {r['match_id']}",
            r["first_innings"]["actual_runs"] == c["actual"]["first_runs"]
            and r["second_innings"]["actual_runs"] == c["actual"]["second_runs"],
        )
        if r["strategies"]:
            for team, trace in r["strategies"].items():
                plan, expected_trace = strategies.plan(
                    team,
                    c["participant_pools"][team],
                    date.fromisoformat(c["date"]),
                    batting_first=team == c["batting_first_team_id"],
                )
                check(
                    f"Prior-only reproducible strategy: {r['variant']} {r['match_id']} {team}",
                    trace == expected_trace
                    and plan.model_dump(mode="json")
                    == report["scenario_plans"][r["match_id"]][team],
                )
    recalculated = summarize(records, all_cases, signature["simulations"])
    for key in (
        "results_by_season",
        "win_correction_fits_development_only",
        "score_correction_fits_development_only",
    ):
        check(f"Recomputed metrics/fits: {key}", recalculated[key] == report[key])
    check(
        "Live-evidence distributional bridge each season",
        {
            r["season"]
            for r in report["live_evidence_adapter_bridge_checks"]
            if r["status"] == "passed"
        }
        == {2024, 2025, 2026},
    )
    result = {
        "status": "passed",
        "passed_checks": len(checks),
        "report_sha256": digest(report_path),
        "database_unchanged_sha256": signature["database_sha256"],
        "forecast_counts": dict(Counter(r["variant"] for r in records)),
        "checks": checks,
        "scope": "artifact_and_temporal_integrity_not_proof_of_calibrated_accuracy",
    }
    (ROOT / "outputs/match-backtest-checks.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in result.items() if key != "checks"}, indent=2))


if __name__ == "__main__":
    main()
