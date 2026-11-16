"""Reproducible full-match backtest; never modifies the saved IPL dataset."""

import argparse
import hashlib
import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import Settings  # noqa: E402
from backend.database import connection  # noqa: E402
from backend.delivery_calibration import CALIBRATION_VERSION, eligible  # noqa: E402
from backend.historical_evidence import HistoricalEvidence, assert_adapter_equivalent  # noqa: E402
from backend.historical_planning import PriorStrategies, historical_cases  # noqa: E402
from backend.match_backtesting import (  # noqa: E402
    PROTOCOL_VERSION,
    anonymous_plans,
    offline_request,
    prediction_record,
    summarize,
)
from backend.services import AnalyticsService  # noqa: E402
from backend.simulation_evidence import SimulationEvidence  # noqa: E402
from backend.simulator import SIMULATOR_VERSION, MatchSimulator  # noqa: E402


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def save(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".pending")
    temporary.write_text(json.dumps(content, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulations", type=int, default=400)
    parser.add_argument("--seed", type=int, default=20261104)
    parser.add_argument("--limit", type=int, help="Smoke test only, explicitly marked incomplete")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/full-match-backtest.json")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not 50 <= args.simulations <= 5000 or not 0 <= args.seed <= 4294967295:
        parser.error("Use 50..5000 simulations and a uint32 seed")
    if args.limit is not None and args.limit < 1:
        parser.error("Limit must be positive")
    started = time.monotonic()
    settings = Settings(Settings.from_env().data_dir, query_timeout_seconds=30)
    database_hash = digest(settings.database)
    source_paths = sorted((ROOT / "backend").glob("*.py")) + [Path(__file__)]
    signature = {
        "protocol_version": PROTOCOL_VERSION,
        "simulator_version": SIMULATOR_VERSION,
        "database_sha256": database_hash,
        "dataset_catalog_sha256": digest(settings.data_dir / "dataset_catalog.json"),
        "source_sha256": {
            str(p.relative_to(ROOT)).replace("\\", "/"): digest(p) for p in source_paths
        },
        "simulations": args.simulations,
        "seed": args.seed,
        "limit": args.limit,
    }
    checkpoint = args.output.with_suffix(".progress.json")
    records, plans_saved, completed = [], {}, set()
    if args.resume and checkpoint.is_file():
        saved = json.loads(checkpoint.read_text("utf-8"))
        if saved["signature"] != signature:
            raise ValueError("Checkpoint code/data/settings do not match this run")
        records, plans_saved = saved["predictions"], saved["scenario_plans"]
        completed = set(saved["completed_match_ids"])
    with connection(settings) as db:
        all_cases, all_exclusions = historical_cases(db, seasons=range(2008, 2027))
        cases = [c for c in all_cases if c["season"] in (2024, 2025, 2026)]
        exclusions = [c for c in all_exclusions if c["season"] in (2024, 2025, 2026)]
        if args.limit:
            cases = cases[: args.limit]
        if not cases:
            raise RuntimeError("No eligible cases")
        strategies = PriorStrategies.from_database(db)
    # A separate read-only connection gets its own SQL deadline, before CPU work.
    with connection(settings) as db:
        evidence_archive = HistoricalEvidence(db, date.fromisoformat(cases[0]["date"]))
    print(
        f"Loaded {len(cases)} matches; {len(exclusions)} format/result exclusions; {len(completed)} resumed.",
        flush=True,
    )
    adapter_checks = []
    for case_index, case in enumerate(cases):
        as_of = date.fromisoformat(case["date"])
        evidence_archive.advance(as_of)
        if case["match_id"] in completed:
            continue
        evidence = evidence_archive.snapshot(case["venue_id"])
        # Verify adapter against live evidence at first case of every season.
        if not any(r["season"] == case["season"] for r in adapter_checks):
            with connection(settings) as db:
                service = AnalyticsService(db, settings, {})
                reference = SimulationEvidence(service, as_of, case["venue_id"])
            a, b = case["team_a_id"], case["team_b_id"]
            pairs = [
                (pid, bowler, phase)
                for pid in case["participant_pools"][a][:3]
                for bowler in case["participant_pools"][b][:3]
                for phase in ("powerplay", "middle", "death")
            ]
            assert_adapter_equivalent(reference, evidence, pairs)
            adapter_checks.append(
                {
                    "season": case["season"],
                    "match_id": case["match_id"],
                    "status": "passed",
                    "pair_phase_checks": len(pairs),
                }
            )
            del reference
        variants = [("population", anonymous_plans(case), None)]
        if case["participant_conditioned_supported"]:
            plans, traces = {}, {}
            for team in (case["team_a_id"], case["team_b_id"]):
                plans[team], traces[team] = strategies.plan(
                    team,
                    case["participant_pools"][team],
                    as_of,
                    batting_first=team == case["batting_first_team_id"],
                )
            plans_saved[case["match_id"]] = {
                team: plan.model_dump(mode="json") for team, plan in plans.items()
            }
            variants += [("participant_raw", plans, traces)]
            # Applying a 2024-fitted correction to 2024 would contaminate the
            # apparent development forecast. The corrected challenger starts 2025.
            if eligible(as_of):
                variants += [("participant_delivery_corrected", plans, traces)]
        case_records = []
        match_seed = (
            args.seed
            + int.from_bytes(hashlib.sha256(case["match_id"].encode()).digest()[:4], "big")
        ) % 4294967296
        for name, plans, traces in variants:
            corrected = name == "participant_delivery_corrected"
            evidence.use_calibration = corrected
            evidence.training["delivery_calibration"] = (
                CALIBRATION_VERSION if corrected else "raw_default"
            )
            evidence.training["calibration_parameters_are_fixed_empirical_estimates"] = corrected
            request = offline_request(case, plans, args.simulations, match_seed, corrected)
            result, _ = MatchSimulator(None, evidence=evidence).run(
                request,
                validated=({}, ["offline_observed_pool_diagnostic_not_verified_prematch_xi"]),
                cpu_seconds=180,
            )
            record = prediction_record(case, result, name, traces)
            record["seed"] = match_seed
            case_records.append(record)
        # A checkpoint never claims a half-computed match is complete.
        records.extend(case_records)
        completed.add(case["match_id"])
        if (case_index + 1) % 5 == 0 or case_index == len(cases) - 1:
            save(
                checkpoint,
                {
                    "signature": signature,
                    "predictions": records,
                    "scenario_plans": plans_saved,
                    "completed_match_ids": sorted(completed),
                    "status": "in_progress_not_a_final_report",
                },
            )
            print(
                f"{case_index + 1}/{len(cases)} {case['date']} {case['match_id']} ({time.monotonic() - started:.1f}s)",
                flush=True,
            )
    if digest(settings.database) != database_hash:
        raise AssertionError("Database changed during evaluation")
    report = summarize(records, all_cases, args.simulations)
    report.update(
        signature=signature,
        total_format_eligible_matches=len(cases),
        participant_pool_cohort_exclusions=[
            {"match_id": c["match_id"], "reason": "not_disjoint_eleven_or_twelve_player_pools"}
            for c in cases
            if not c["participant_conditioned_supported"]
        ],
        format_result_exclusions=exclusions,
        scenario_plans=plans_saved,
        live_evidence_adapter_bridge_checks=adapter_checks,
        database_unchanged=True,
        completed_at=datetime.now(timezone.utc).isoformat(),
        elapsed_seconds=round(time.monotonic() - started, 3),
        complete_requested_cohort=args.limit is None,
    )
    if args.limit:
        report["status"] = "limited_smoke_test_not_full_backtest"
    save(args.output, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "cohorts": report["cohort_counts"],
                "elapsed_seconds": report["elapsed_seconds"],
                "output": str(args.output),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
