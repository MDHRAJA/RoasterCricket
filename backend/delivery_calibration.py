"""Bounded joint probability correction; raw Bayesian posterior remains separately visible."""

from datetime import date

import numpy as np
from scipy.optimize import minimize
from scipy.special import logsumexp

from backend.bayesian import EVENT_MASKS, OUTCOMES

CALIBRATION_VERSION = "joint-event-logit-2024-v1"
CALIBRATION_CUTOFF = date(2025, 1, 1)
# Frozen from 2024 prequential predictions only; evaluation script reproduces fitting.
OFFSETS = np.array([0.15614920048857436, -0.03169681980336517, 0.1059841253397679])
READY = True
BASIS = np.array(
    [[boundary, int(runs == 0), dismissed] for runs, boundary, dismissed in OUTCOMES], dtype=float
)
FIXED_WEIGHTS = np.exp(BASIS @ OFFSETS)


def corrected_draw(probabilities):
    """Fast path for already-valid internal posterior draws; bounded fixed weights."""
    weighted = probabilities * FIXED_WEIGHTS
    return weighted / weighted.sum()


def corrected(probabilities, offsets=OFFSETS):
    probabilities = np.asarray(probabilities, dtype=float)
    if (
        probabilities.ndim < 1
        or probabilities.shape[-1] != len(OUTCOMES)
        or not np.all(np.isfinite(probabilities))
        or np.any(probabilities < 0)
        or not np.allclose(probabilities.sum(axis=-1), 1)
    ):
        raise ValueError("Correction requires finite normalized joint probabilities")
    weighted = probabilities * (FIXED_WEIGHTS if offsets is OFFSETS else np.exp(BASIS @ offsets))
    return weighted / weighted.sum(axis=-1, keepdims=True)


def fit(probabilities, counts):
    """Three offsets, symmetric L2 penalty 10 and [-.75,.75] bounds, fixed in advance."""
    probabilities, counts = np.asarray(probabilities), np.asarray(counts)
    if (
        probabilities.shape != counts.shape
        or probabilities.ndim != 2
        or probabilities.shape[1] != len(OUTCOMES)
    ):
        raise ValueError("Calibration requires aligned joint probabilities and counts")
    if (
        not np.all(np.isfinite(probabilities))
        or not np.all(np.isfinite(counts))
        or np.any(probabilities <= 0)
        or np.any(counts < 0)
        or not counts.sum()
    ):
        raise ValueError(
            "Calibration inputs must have positive probabilities and nonnegative evidence"
        )
    if not np.allclose(probabilities.sum(axis=1), 1):
        raise ValueError("Joint probabilities must sum to one")
    logs, totals = np.log(probabilities), counts.sum(axis=1)
    observed_events = (counts @ BASIS).sum(axis=0)

    def objective(offsets):
        shifted = logs + BASIS @ offsets
        normalizer = logsumexp(shifted, axis=1)
        p = np.exp(shifted - normalizer[:, None])
        loss = float(-(counts * shifted).sum() + totals @ normalizer + 5 * (offsets @ offsets))
        gradient = ((p @ BASIS) * totals[:, None]).sum(axis=0) - observed_events + 10 * offsets
        return loss, gradient

    result = minimize(
        objective, np.zeros(3), jac=True, method="L-BFGS-B", bounds=[(-0.75, 0.75)] * 3
    )
    if not result.success or not np.all(np.isfinite(result.x)):
        raise ValueError("Calibration fit failed convergence/finite-value checks")
    return result.x


def eligible(as_of):
    return READY and as_of >= CALIBRATION_CUTOFF


def forecast(probabilities, as_of, *, supported_context):
    if not supported_context or not eligible(as_of):
        return {
            "status": "not_applied",
            "reason": "unvalidated_context_or_before_calibration_cutoff",
            "version": CALIBRATION_VERSION,
        }
    p = corrected(probabilities)
    return {
        "status": "experimental_calibration_candidate",
        "version": CALIBRATION_VERSION,
        "fit_season": 2024,
        "exclusive_fit_cutoff": CALIBRATION_CUTOFF.isoformat(),
        "offsets_boundary_dot_dismissal": OFFSETS.tolist(),
        "events": {
            name: {"probability": float(p[mask].sum())} for name, mask in EVENT_MASKS.items()
        },
        "joint_outcomes": [
            {
                "batter_runs": "7+" if runs == 7 else str(runs),
                "boundary": bool(boundary),
                "striker_dismissed": bool(out),
                "probability": float(p[i]),
            }
            for i, (runs, boundary, out) in enumerate(OUTCOMES)
        ],
        "expected_capped_batter_runs_per_legal_delivery": float(
            p @ np.array([r for r, _, _ in OUTCOMES])
        ),
        "intervals": None,
        "interpretation": "normalized_joint_logit_correction_not_replacement_Bayesian_credible_intervals",
        "limitations": [
            "calibration_parameter_uncertainty_not_propagated",
            "delivery_backtest_not_match_win_calibration",
        ],
    }
