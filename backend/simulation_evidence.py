"""One bounded archive read per planning request; memoized matchup posteriors."""

from collections import defaultdict
from datetime import timedelta

import numpy as np

from backend.backtesting import RollingIndex
from backend.bayesian import DEFAULT_CONFIG, OUTCOMES, K, outcome_index, posterior
from backend.delivery_calibration import CALIBRATION_VERSION, corrected_draw, eligible
from backend.services import ApiError


class SimulationEvidence:
    def __init__(self, analytics, as_of, venue_id, *, use_calibration=False):
        self.as_of, self.venue_id = as_of, venue_id
        self.use_calibration = use_calibration and eligible(as_of)
        start = as_of - timedelta(days=DEFAULT_CONFIG.lookback_days)
        rows = analytics.db.execute(
            """SELECT batter_id,bowler_id,phase,venue_id,batter_runs,
            COALESCE(four,0),COALESCE(six,0),striker_dismissed,legal_ball,
            COALESCE(wides,0),COALESCE(noballs,0),COALESCE(byes,0),COALESCE(legbyes,0),
            COALESCE(team_wickets,0),COALESCE(bowler_wicket,0),match_date FROM deliveries
            WHERE is_super_over=0 AND match_date>=? AND match_date<?""",
            (start.isoformat(), as_of.isoformat()),
        ).fetchall()
        if not rows:
            raise ApiError(
                503,
                "no_training_evidence",
                "No eligible deliveries in the simulation training window",
            )
        wicket_counts = analytics.db.execute(
            """SELECT COUNT(*) AS n,
            SUM(CASE WHEN w.kind='run out' OR w.kind='obstructing the field' THEN 1 ELSE 0 END) AS allowed
            FROM wickets w JOIN deliveries d USING(delivery_id)
            WHERE d.is_super_over=0 AND d.legal_ball=1 AND w.player_out_id=d.batter_id
            AND w.counts_as_team_wicket=1 AND d.match_date>=? AND d.match_date<?""",
            (start.isoformat(), as_of.isoformat()),
        ).fetchone()
        self.index, self.cache = RollingIndex(), {}
        grouped = defaultdict(lambda: np.zeros(K))
        self.types = defaultdict(lambda: np.zeros(3))
        self.prototypes = defaultdict(list)
        self.tails = []
        for row in rows:
            (
                b,
                w,
                phase,
                venue,
                runs,
                four,
                six,
                dismissed,
                legal,
                wide,
                noball,
                byes,
                legbyes,
                wickets,
                bowler_wicket,
                day,
            ) = row
            kind = 0 if legal else 1 if wide else 2
            context = (phase, venue)
            self.types[None][kind] += 1
            self.types[context][kind] += 1
            # role: original striker=1, non-striker=2. More than one dismissal
            # per record is not a supported physical delivery.
            role = 1 if dismissed else 2 if wickets else 0
            if legal:
                grouped[(b, w, context)][outcome_index(runs, int(four or six), dismissed)] += 1
                if runs >= 7:
                    self.tails.append(int(runs))
                if runs == 0 and not dismissed:
                    prototype = (int(byes), int(legbyes), role)
                    self.prototypes[(None, "legal_zero")].append(prototype)
                    self.prototypes[(context, "legal_zero")].append(prototype)
                if runs > 0 and not dismissed and not four and not six:
                    prototype = int(role == 2)
                    self.prototypes[(None, "running_non_striker_out")].append(prototype)
                    self.prototypes[(context, "running_non_striker_out")].append(prototype)
            else:
                prototype = (
                    int(runs),
                    int(wide),
                    int(noball),
                    int(byes),
                    int(legbyes),
                    bool(four or six),
                    role,
                    bool(bowler_wicket),
                )
                self.prototypes[(None, kind)].append(prototype)
                self.prototypes[(context, kind)].append(prototype)
        for (b, w, ctx), counts in grouped.items():
            self.index.add(b, w, ctx, counts)
        if not self.index.get(0, None).sum():
            raise ApiError(
                503,
                "no_legal_training_evidence",
                "No legal deliveries are available for simulation",
            )
        self.type_cdfs = {
            phase: np.cumsum(self.delivery_types(phase))
            for phase in ("powerplay", "middle", "death")
        }
        self.free_hit_dismissal_share = (
            float((wicket_counts[1] or 0) / wicket_counts[0]) if wicket_counts[0] else 0.03
        )
        self.training = {
            "window_start": start.isoformat(),
            "exclusive_cutoff": as_of.isoformat(),
            "first_included_date": min(r[-1] for r in rows),
            "last_included_date": max(r[-1] for r in rows),
            "recorded_deliveries": len(rows),
            "legal_deliveries": int(self.index.get(0, None).sum()),
            "legal_striker_wicket_mode_records": int(wicket_counts[0]),
            "supplemental_model": "empirical_venue_phase_bootstrap_with_global_pooling",
            "profile_attributes_used_for_lineup_constraints_not_delivery_model": True,
            "delivery_calibration": CALIBRATION_VERSION if self.use_calibration else "raw_default",
            "calibration_parameters_are_fixed_empirical_estimates": self.use_calibration,
        }

    def alpha(self, batter, bowler, phase):
        key = (batter, bowler, phase)
        if key not in self.cache:
            pools = self.index.pools(batter, bowler, (phase, self.venue_id))
            self.cache[key] = (posterior(pools)[0], int(pools["target"].sum()))
        return self.cache[key]

    def delivery_types(self, phase):
        global_counts = self.types[None]
        local = self.types[(phase, self.venue_id)]
        mean = global_counts / global_counts.sum()
        return (local + 100 * mean) / (local.sum() + 100)

    def prototype(self, rng, phase, kind, fallback):
        local = self.prototypes[((phase, self.venue_id), kind)]
        global_values = self.prototypes[(None, kind)]
        values = local if local and rng.random() < len(local) / (len(local) + 20) else global_values
        return values[int(rng.integers(len(values)))] if values else fallback

    def prepared(self, batting, bowling):
        for batter in batting:
            for bowler in set(bowling):
                for phase in ("powerplay", "middle", "death"):
                    self.alpha(batter, bowler, phase)

    def sample_joint(self, rng, batter, bowler, phase, draws, posterior_sampling, free_hit):
        key = (batter, bowler, phase)
        if key not in draws:
            alpha, _ = self.alpha(*key)
            probabilities = rng.dirichlet(alpha) if posterior_sampling else alpha / alpha.sum()
            if self.use_calibration:
                probabilities = corrected_draw(probabilities)
            # Boundary plus dismissal is not a physical supported scoring event.
            # Transfer impossible/illegal dismissal mass to its survival counterpart.
            for i, (_runs, boundary, dismissed) in enumerate(OUTCOMES):
                if dismissed and boundary:
                    probabilities[i - 1] += probabilities[i]
                    probabilities[i] = 0
            free_probabilities = probabilities.copy()
            for i, (_, _, dismissed) in enumerate(OUTCOMES):
                if dismissed:
                    retained = free_probabilities[i] * self.free_hit_dismissal_share
                    free_probabilities[i - 1] += free_probabilities[i] - retained
                    free_probabilities[i] = retained
            draws[key] = (np.cumsum(probabilities), np.cumsum(free_probabilities))
        i = int(np.searchsorted(draws[key][int(free_hit)], rng.random(), side="right"))
        runs, boundary, dismissed = OUTCOMES[min(i, K - 1)]
        if runs == 7:
            runs = self.tails[int(rng.integers(len(self.tails)))] if self.tails else 7
        return int(runs), bool(boundary), bool(dismissed)
