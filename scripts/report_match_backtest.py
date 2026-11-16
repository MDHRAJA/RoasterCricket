"""Score the width/coverage trade-off and write an honest model-readiness report."""

import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.match_backtesting import corrected_score_records, innings_metrics  # noqa: E402
from backend.simulator import wilson  # noqa: E402


def interval_score(actual, lower, upper, alpha):
    """Unweighted central interval/Winkler score: smaller is better."""
    if not 0 < alpha < 1 or lower > upper:
        raise ValueError("Invalid interval or tail probability")
    return upper - lower + 2 / alpha * (max(0, lower - actual) + max(0, actual - upper))


def paired_date_gain(raw, candidate, loss):
    if len(raw) != len(candidate) or not raw:
        raise ValueError("Need nonempty aligned paired forecasts")
    daily = defaultdict(lambda: np.zeros(2))
    for a, b in zip(raw, candidate, strict=True):
        if (a["match_id"], a["date"]) != (b["match_id"], b["date"]):
            raise ValueError("Forecasts are not aligned")
        daily[a["date"]] += [loss(a) - loss(b), 1]
    values = np.array([daily[key] for key in sorted(daily)])
    rng = np.random.default_rng(20261104)
    draws = values[rng.integers(len(values), size=(2000, len(values)))]
    gains = draws[:, :, 0].sum(axis=1) / draws[:, :, 1].sum(axis=1)
    return {
        "mean_gain": float(values[:, 0].sum() / values[:, 1].sum()),
        "95_percent_date_cluster_interval": [float(v) for v in np.quantile(gains, [0.025, 0.975])],
        "positive_means_candidate_better": True,
        "resamples": 2000,
        "limitations": "retrospective paired diagnostic; excludes fit/selection/season-dependence uncertainty",
    }


def distribution_metrics(records):
    result = {"point_and_coverage": innings_metrics(records), "interval_scores": {}}
    for level, lo, hi in ((0.8, "p10", "p90"), (0.9, "p05", "p95")):
        rows = [r["first_innings"] for r in records]
        covered = sum(
            row["score_quantiles"][lo] <= row["actual_runs"] <= row["score_quantiles"][hi]
            for row in rows
        )
        result["interval_scores"][str(level)] = {
            "mean_interval_score": float(
                np.mean(
                    [
                        interval_score(
                            row["actual_runs"],
                            row["score_quantiles"][lo],
                            row["score_quantiles"][hi],
                            1 - level,
                        )
                        for row in rows
                    ]
                )
            ),
            "covered_matches": covered,
            "total_matches": len(rows),
            "coverage_wilson_95_interval": {
                **wilson(covered, len(rows)),
                "interpretation": "historical_coverage_binomial_independence_approximation_not_a_guarantee",
            },
            "coverage_interval_caveat": "binomial independence approximation, not a temporal coverage guarantee",
        }
    return result


def evaluate_score_challengers(report):
    result = {}
    for year in (2025, 2026):
        result[str(year)] = {}
        for name in ("population", "participant_raw"):
            rows = [
                r for r in report["predictions"] if r["season"] == year and r["variant"] == name
            ]
            fitted = report["score_correction_fits_development_only"][name]
            candidate = corrected_score_records(rows, fitted)
            if not candidate:
                continue
            comparisons = {
                "absolute_run_error": paired_date_gain(
                    rows,
                    candidate,
                    lambda r: abs(
                        r["first_innings"]["mean_runs"] - r["first_innings"]["actual_runs"]
                    ),
                )
            }
            for level, lo, hi in ((0.8, "p10", "p90"), (0.9, "p05", "p95")):

                def loss(record, level=level, lo=lo, hi=hi):
                    row = record["first_innings"]
                    return interval_score(
                        row["actual_runs"],
                        row["score_quantiles"][lo],
                        row["score_quantiles"][hi],
                        1 - level,
                    )

                comparisons[f"interval_score_{level}"] = paired_date_gain(rows, candidate, loss)
            result[str(year)][name] = {
                "raw": distribution_metrics(rows),
                "candidate": distribution_metrics(candidate),
                "paired_gain": comparisons,
            }
    return result


def markdown(report, evaluation):
    counts = report["cohort_counts"]
    simulations = sum(counts.values()) * report["simulations_per_match_per_variant"]
    fitted = report["score_correction_fits_development_only"]["participant_raw"]
    raw_2025 = report["results_by_season"]["2025"]["variants"]["participant_raw"]["win_metrics"]
    corrected_2025 = report["results_by_season"]["2025"]["variants"][
        "participant_delivery_corrected"
    ]["win_metrics"]
    report_date = datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat()
    lines = [
        f"# Full-match backtest results - {report_date}",
        "",
        "The complete retrospective run found that the current player-based winner model is **not decision-ready**. The 2024-fitted score-distribution correction improves some uncertainty diagnostics, but is not enabled in serving. A conditional observed-participant-pool diagnostic must not be relabeled as verified pre-match-XI accuracy.",
        "",
        f"Evaluated {report['total_format_eligible_matches']} complete ordinary matches across 2024-2026, with {report['simulations_per_match_per_variant']} simulations per match/variant. There are {counts['population']} anonymous forecasts, {counts['participant_raw']} player-based forecasts and {counts['participant_delivery_corrected']} optional delivery-corrected forecasts (2025 onward only), totaling {simulations:,} simulated matches. {len(report['format_result_exclusions'])} source matches failed the format/result screen; {len(report['participant_pool_cohort_exclusions'])} otherwise eligible participant pools were unsupported. 2024 is development data; later seasons had already been inspected for other diagnostics. No new prospective trial is claimed.",
        "",
        "## Winner predictions: player-based raw model",
        "",
        "These forecasts condition on recorded post-match participant pools and hypothetical prior-only tactics, not verified announced XIs. Win metrics condition on decisive trials. At exactly 50% probability, threshold accuracy receives half credit.",
        "",
        "| Evaluation season | Matches | Top-pick accuracy | Brier score | Log loss | Neutral Brier / log loss |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for year in (2025, 2026):
        v = report["results_by_season"][str(year)]["variants"]["participant_raw"]
        w = v["win_metrics"]
        lines.append(
            f"| {year} | {w['matches']} | {100 * w['top_pick_accuracy_with_half_credit_for_50_percent_ties']:.1f}% | {w['brier_score']:.4f} | {w['log_loss']:.4f} | 0.2500 / 0.6931 |"
        )
    lines += [
        "",
        "Lower Brier/log loss is better. Neither year establishes an advantage over neutral, and paired intervals cross zero. Population-only simulations also fail to establish an advantage. There is no supported claim of 60-70% match prediction accuracy. A majority-class threshold baseline can exceed 50% accuracy when batting-first win rates are uneven, so threshold accuracy alone is not a calibration test.",
        "",
        f"The optional delivery correction improves first-innings run bias but makes 2025 winner metrics worse (Brier {corrected_2025['brier_score']:.4f} versus raw {raw_2025['brier_score']:.4f}); 2026 is mixed. The development-fitted win correction also does not provide consistent cross-season improvement. Neither is promoted.",
        "",
        "## First-innings uncertainty: frozen 2024 score correction",
        "",
        f"The participant-model candidate adds about {fitted['mean_shift_runs']:.2f} runs to the predicted mean and multiplies interval deviations by {fitted['interval_scale']:.3f}. It does not rerun physical matches or change winner probabilities. All coefficients were fitted on 2024; the following comparisons use 2025/2026 only.",
        "",
        "| Season | Run MAE raw → candidate | Nominal 90% coverage raw → candidate | Mean 90% width raw → candidate | 90% interval score raw → candidate |",
        "| --- | --- | --- | --- | --- |",
    ]
    for year in (2025, 2026):
        e = evaluation[str(year)]["participant_raw"]
        a, b = e["raw"]["point_and_coverage"], e["candidate"]["point_and_coverage"]
        i, j = e["raw"]["interval_scores"]["0.9"], e["candidate"]["interval_scores"]["0.9"]
        lines.append(
            f"| {year} | {a['mae_runs']:.2f} → {b['mae_runs']:.2f} | {100 * a['predictive_coverage']['0.9']:.1f}% → {100 * b['predictive_coverage']['0.9']:.1f}% | {a['mean_interval_width']['0.9']:.1f} → {b['mean_interval_width']['0.9']:.1f} runs | {i['mean_interval_score']:.2f} → {j['mean_interval_score']:.2f} |"
        )
    lines += [
        "",
        "Interval score penalizes both excessive width and misses; lower is better. This matters because coverage alone can be increased by widening every interval. Paired date-cluster comparisons and approximate coverage confidence intervals are saved in `outputs/match-score-calibration-audit.json`. Small seasonal cohorts, temporal dependence, finite simulation draws, participant-pool conditioning and parameter/model-selection uncertainty prevent a calibrated-accuracy guarantee. Point-error improvements are small and their uncertainty must be inspected, not advertised as assured gains.",
        "",
        "## Shipped reliability changes",
        "",
        "- The offline evaluator runs the same complete two-innings engine as the API, with a faster rolling adapter checked against live evidence in each evaluated season.",
        "- Strategies use preceding-date batting positions and bowling usage, never the target's actual batting order or realized bowling schedule. Hypothetical Impact choices remain explicitly conditional and unverified.",
        "- Match/XI audits distinguish all prepared matchup contexts from legal-event draws actually exposed during simulation. Sparse-history warnings now have both denominators.",
        "- Innings responses include p05/p95 quantiles, predictive score standard deviation and Monte Carlo standard error of the mean. Simulation precision remains distinct from predictive accuracy.",
        "- Date/code/data signatures, per-match seeds, atomic resume checkpoints, explicit exclusions and independent artifact checks make the results reproducible. The source database is unchanged.",
        "- Production validation, verified eligibility and historical XI counterfactual benefit remain false. Optional delivery correction stays off by default; new win/score corrections are diagnostic-only.",
        "",
        "## Next reliability priorities",
        "",
        "1. Verify timestamped announced XIs and date-valid eligible substitutes instead of conditioning on observed participant pools.",
        "2. Develop and validate innings/score-pressure, recent-form and regime features. Current raw score intervals substantially under-cover; match-level variability needs explicit modeling rather than merely more trials.",
        "3. Compare against post-toss batting-order/venue baselines on matched cases, and assess conditional-lineup strategies separately from optimizer counterfactuals.",
        "4. Reserve genuinely new matches for prospective evaluation before presenting a win estimate or XI recommendation as reliable.",
        "",
        "Reproduce: `scripts/backtest_matches.py`, `scripts/check_match_backtest.py`, then `scripts/report_match_backtest.py`. Full protocol and caveats: [evaluation guide](full-match-backtesting.md). Machine-readable forecasts/provenance: `outputs/full-match-backtest.json`; integrity checks: `outputs/match-backtest-checks.json`.",
        "",
        "Method reference: [official scoringrules interval-score documentation](https://scoringrules.readthedocs.io/en/latest/generated/scoringrules.interval_score.html). The implementation uses existing NumPy/SciPy dependencies; no scoringrules package is installed.",
    ]
    return "\n".join(lines) + "\n"


def main():
    path = ROOT / "outputs/full-match-backtest.json"
    report = json.loads(path.read_text("utf-8"))
    if not report["complete_requested_cohort"]:
        raise ValueError("A smoke/checkpoint artifact cannot generate a final report")
    evaluation = evaluate_score_challengers(report)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    audit = {
        "source_report_sha256": digest,
        "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "status": "retrospective_diagnostic_only",
        "score_correction_enabled_in_serving": False,
        "results": evaluation,
        "interval_score_reference": "https://scoringrules.readthedocs.io/en/latest/generated/scoringrules.interval_score.html",
    }
    (ROOT / "outputs/match-score-calibration-audit.json").write_text(
        json.dumps(audit, indent=2) + "\n", encoding="utf-8"
    )
    (ROOT / "docs/full-match-results.md").write_text(markdown(report, evaluation), encoding="utf-8")
    print(
        json.dumps(
            {year: values["participant_raw"]["paired_gain"] for year, values in evaluation.items()},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
