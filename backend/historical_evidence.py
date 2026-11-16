"""Rolling offline adapter for the SAME delivery sampler used by the live API.

Read the archive once; advance whole date blocks only after earlier predictions.
This adapter does not change posterior or supplemental-event equations.
"""

from bisect import bisect_left
from collections import Counter, defaultdict, deque
from datetime import timedelta
from itertools import groupby

import numpy as np

from backend.backtesting import RollingIndex
from backend.bayesian import DEFAULT_CONFIG, K, outcome_index
from backend.delivery_calibration import CALIBRATION_VERSION, eligible
from backend.simulation_evidence import SimulationEvidence


class HistoricalEvidence:
    def __init__(self, db, first_date):
        self.index = RollingIndex()
        self.types = defaultdict(lambda: np.zeros(3))
        self.samples = defaultdict(lambda: [[], []])
        self.tails = [[], []]
        self.active = deque()
        self.as_of = None
        start = (first_date - timedelta(days=DEFAULT_CONFIG.lookback_days)).isoformat()
        grouped = defaultdict(lambda: defaultdict(lambda: np.zeros(K)))
        for r in db.execute(
            """SELECT match_date,batter_id,bowler_id,phase,venue_id,
            MIN(batter_runs,7) AS runs,CASE WHEN four=1 OR six=1 THEN 1 ELSE 0 END AS boundary,
            striker_dismissed,COUNT(*) AS n FROM deliveries WHERE legal_ball=1
            AND is_super_over=0 AND match_date>=?
            GROUP BY match_date,batter_id,bowler_id,phase,venue_id,runs,boundary,striker_dismissed
            ORDER BY match_date""",
            (start,),
        ):
            grouped[r["match_date"]][r["batter_id"], r["bowler_id"], (r["phase"], r["venue_id"])][
                outcome_index(r["runs"], r["boundary"], r["striker_dismissed"])
            ] += r["n"]
        daily = {}
        rows = db.execute(
            """SELECT match_date,phase,venue_id,batter_runs,COALESCE(four,0),
            COALESCE(six,0),striker_dismissed,legal_ball,COALESCE(wides,0),COALESCE(noballs,0),
            COALESCE(byes,0),COALESCE(legbyes,0),COALESCE(team_wickets,0),COALESCE(bowler_wicket,0)
            FROM deliveries WHERE is_super_over=0 AND match_date>=?
            ORDER BY match_date,match_id,innings,sequence_in_innings""",
            (start,),
        )
        for day, chunk in groupby(rows, key=lambda r: r[0]):
            types = defaultdict(lambda: np.zeros(3))
            count = 0
            for r in chunk:
                _, phase, venue, runs, four, six, out, legal, wide, nb, byes, lb, wkts, bw = r
                kind = 0 if legal else 1 if wide else 2
                context = (phase, venue)
                types[None][kind] += 1
                types[context][kind] += 1
                count += 1
                role = 1 if out else 2 if wkts else 0
                prototype_kind = None
                if legal:
                    if runs >= 7:
                        self.tails[0].append(day)
                        self.tails[1].append(int(runs))
                    if runs == 0 and not out:
                        prototype_kind, value = "legal_zero", (int(byes), int(lb), role)
                    elif runs > 0 and not out and not four and not six:
                        prototype_kind, value = "running_non_striker_out", int(role == 2)
                else:
                    prototype_kind = kind
                    value = (
                        int(runs),
                        int(wide),
                        int(nb),
                        int(byes),
                        int(lb),
                        bool(four or six),
                        role,
                        bool(bw),
                    )
                if prototype_kind is not None:
                    for key in ((None, prototype_kind), (context, prototype_kind)):
                        self.samples[key][0].append(day)
                        self.samples[key][1].append(value)
            daily[day] = (dict(types), count)
        modes = {
            r[0]: (int(r[1]), int(r[2] or 0))
            for r in db.execute(
                """SELECT d.match_date,COUNT(*),SUM(CASE WHEN
                w.kind IN ('run out','obstructing the field') THEN 1 ELSE 0 END)
                FROM wickets w JOIN deliveries d USING(delivery_id)
                WHERE d.is_super_over=0 AND d.legal_ball=1 AND w.player_out_id=d.batter_id
                AND w.counts_as_team_wicket=1 AND d.match_date>=? GROUP BY d.match_date""",
                (start,),
            )
        }
        self.days = [
            (day, dict(grouped.get(day, {})), daily[day][0], daily[day][1], modes.get(day, (0, 0)))
            for day in sorted(daily)
        ]
        self.cursor = 0
        self.records = 0
        self.wicket_modes = np.zeros(2, dtype=int)

    def _update(self, block, sign):
        _, groups, types, count, modes = block
        for (batter, bowler, context), counts in groups.items():
            self.index.add(batter, bowler, context, counts, sign=sign)
        for key, counts in types.items():
            self.types[key] += sign * counts
        self.records += sign * count
        self.wicket_modes += sign * np.array(modes)

    def advance(self, as_of):
        if self.as_of is not None and as_of < self.as_of:
            raise ValueError("Historical evidence cannot move backwards")
        day = as_of.isoformat()
        start = (as_of - timedelta(days=DEFAULT_CONFIG.lookback_days)).isoformat()
        while self.cursor < len(self.days) and self.days[self.cursor][0] < day:
            block = self.days[self.cursor]
            if block[0] >= start:
                self._update(block, 1)
                self.active.append(block)
            self.cursor += 1
        while self.active and self.active[0][0] < start:
            self._update(self.active.popleft(), -1)
        self.as_of = as_of

    def snapshot(self, venue_id, *, use_calibration=False):
        if not self.active or self.as_of is None:
            raise ValueError("Historical evidence needs earlier training matches")
        cutoff = self.as_of.isoformat()
        start = (self.as_of - timedelta(days=DEFAULT_CONFIG.lookback_days)).isoformat()
        if not start <= self.active[0][0] <= self.active[-1][0] < cutoff:
            raise AssertionError("Future, same-day or expired evidence entered the adapter")
        result = object.__new__(SimulationEvidence)
        result.as_of, result.venue_id = self.as_of, venue_id
        result.index, result.cache = self.index, {}
        result.use_calibration = bool(use_calibration and eligible(self.as_of))
        result.types = self.types
        result.prototypes = defaultdict(list)
        for key, (dates, values) in self.samples.items():
            if key[0] is None or key[0][1] == venue_id:
                lo, hi = bisect_left(dates, start), bisect_left(dates, cutoff)
                result.prototypes[key] = values[lo:hi]
        dates, values = self.tails
        result.tails = values[bisect_left(dates, start) : bisect_left(dates, cutoff)]
        result.type_cdfs = {
            phase: np.cumsum(result.delivery_types(phase))
            for phase in ("powerplay", "middle", "death")
        }
        n, allowed = (int(v) for v in self.wicket_modes)
        result.free_hit_dismissal_share = allowed / n if n else 0.03
        result.training = {
            "window_start": start,
            "exclusive_cutoff": cutoff,
            "first_included_date": self.active[0][0],
            "last_included_date": self.active[-1][0],
            "recorded_deliveries": int(self.records),
            "legal_deliveries": int(self.index.get(0, None).sum()),
            "legal_striker_wicket_mode_records": n,
            "supplemental_model": "empirical_venue_phase_bootstrap_with_global_pooling",
            "profile_attributes_used_for_lineup_constraints_not_delivery_model": True,
            "delivery_calibration": CALIBRATION_VERSION
            if result.use_calibration
            else "raw_default",
            "calibration_parameters_are_fixed_empirical_estimates": result.use_calibration,
            "offline_adapter": "date_blocked_sufficient_statistics_same_sampler",
        }
        return result


def assert_adapter_equivalent(reference, adapted, pairs):
    """Distributional bridge check, including supplemental events, not just means."""
    for batter, bowler, phase in pairs:
        a, n = reference.alpha(batter, bowler, phase)
        b, m = adapted.alpha(batter, bowler, phase)
        if n != m or not np.allclose(a, b, rtol=1e-12, atol=1e-12):
            raise AssertionError("Historical adapter posterior differs from live evidence")
    if not np.isclose(reference.free_hit_dismissal_share, adapted.free_hit_dismissal_share):
        raise AssertionError("Historical adapter wicket-mode share differs")
    for phase in ("powerplay", "middle", "death"):
        if not np.allclose(reference.type_cdfs[phase], adapted.type_cdfs[phase]):
            raise AssertionError("Historical adapter delivery types differ")
        for kind in ("legal_zero", "running_non_striker_out", 1, 2):
            for context in (None, (phase, reference.venue_id)):
                key = context, kind
                if Counter(reference.prototypes[key]) != Counter(adapted.prototypes[key]):
                    raise AssertionError("Historical adapter supplemental distribution differs")
    if Counter(reference.tails) != Counter(adapted.tails):
        raise AssertionError("Historical adapter tail distribution differs")
    for field in (
        "recorded_deliveries",
        "legal_deliveries",
        "first_included_date",
        "last_included_date",
    ):
        if reference.training[field] != adapted.training[field]:
            raise AssertionError(f"Historical adapter training trace differs: {field}")
