import snapshot from './snapshots/record.json';

export interface Interval {
  lower: number;
  upper: number;
}
export interface Gain extends Interval {
  mean: number;
}
export interface CalibrationBin extends Interval {
  n: number;
  mean: number;
  observed: number;
  wins: number;
  interval: Interval;
}
export interface RecordMetrics {
  n: number;
  correct: number | null;
  accuracy: number;
  brier: number;
  logLoss: number;
  ece: number;
  bins: CalibrationBin[];
}
export interface ResearchForecast {
  id: string;
  date: string;
  season: number;
  first: string;
  chase: string;
  ground: string;
  probability: number;
  outcome: number;
  latestEvidence: string | null;
}
export interface SeasonRecord {
  season: number;
  phase: string;
  metrics: RecordMetrics;
}
export type SimulatorVariant = 'population' | 'participant_raw' | 'participant_delivery_corrected';
export interface SimulatorEvaluation {
  metrics: RecordMetrics;
  neutral: RecordMetrics;
  orderBaseline: RecordMetrics;
  gain: { brier: Gain; log_loss: Gain };
}
export interface ScoreEvidence {
  n: number;
  mae: number;
  coverage: number;
  width: number;
  intervalScore: number;
  covered: number;
  interval: Interval;
}
export interface ScoreComparison {
  raw: ScoreEvidence;
  candidate: ScoreEvidence;
  maeGain: Gain;
  intervalGain: Gain;
}
export interface SimulatorSeason {
  season: number;
  variants: Record<SimulatorVariant, SimulatorEvaluation>;
  scores: Record<'population' | 'participant_raw', ScoreComparison>;
}
export interface DeliveryMetrics {
  n: number;
  matches: number;
  loss: number;
  events: Record<'boundary' | 'dot' | 'striker_dismissal', { ece: number; brier: number }>;
}
export interface RecordData {
  schema: string;
  exportedAt: string;
  databaseSha256: string;
  sources: { path: string; sha256: string }[];
  winner: {
    recipe: string;
    target: number;
    targetMet: boolean;
    lockedAt: string;
    trainingStart: number;
    selectionRecipes: number;
    macroValidationAccuracy: number;
    integrityChecks: number;
    seasons: SeasonRecord[];
    accuracyInterval: Interval;
    baselines: Record<
      'neutral_50_percent_ties_choose_chase' | 'prior_order_history',
      RecordMetrics
    >;
    pairedGains: Record<
      'neutral_50_percent_ties_choose_chase' | 'prior_order_history',
      { brier: Gain; log_loss: Gain }
    >;
    discordance: { model_only_correct: number; chase_only_correct: number };
    forecasts: ResearchForecast[];
    limitations: string[];
  };
  simulator: {
    completedAt: string;
    version: string;
    trials: number;
    cohorts: Record<SimulatorVariant, number>;
    eligible: number;
    formatExclusions: { match_id: string; season: number; reason: string }[];
    poolExclusions: { match_id: string; reason: string }[];
    integrityChecks: number;
    seasons: SimulatorSeason[];
    limitations: string[];
  };
  delivery: {
    version: string;
    completedAt: string;
    fitDeliveries: number;
    fitCutoff: string;
    seasons: { season: number; raw: DeliveryMetrics; corrected: DeliveryMetrics; gain: Gain }[];
    limitations: string[];
  };
}
export const recordData: RecordData = snapshot;

// Check the public projection as well as the exporter's source-artifact checks.
// Invalid evidence is withheld rather than partially displayed as a successful audit.
export function validateRecord(data: RecordData) {
  const probability = (n: number) => Number.isFinite(n) && n >= 0 && n <= 1;
  const interval = (v: Interval) =>
    probability(v.lower) && probability(v.upper) && v.lower <= v.upper;
  const near = (a: number, b: number) => Math.abs(a - b) < 1e-9;
  function validMetrics(m: RecordMetrics) {
    return (
      Number.isInteger(m.n) &&
      m.n > 0 &&
      probability(m.accuracy) &&
      probability(m.brier) &&
      Number.isFinite(m.logLoss) &&
      m.logLoss >= 0 &&
      probability(m.ece) &&
      (m.correct === null ||
        (Number.isInteger(m.correct) &&
          m.correct >= 0 &&
          m.correct <= m.n &&
          near(m.correct / m.n, m.accuracy))) &&
      m.bins.reduce((sum, b) => sum + b.n, 0) === m.n &&
      m.bins.every(
        (b) =>
          Number.isInteger(b.n) &&
          b.n > 0 &&
          Number.isInteger(b.wins) &&
          b.wins >= 0 &&
          b.wins <= b.n &&
          interval(b) &&
          probability(b.mean) &&
          b.mean >= b.lower &&
          b.mean <= b.upper &&
          near(b.wins / b.n, b.observed) &&
          interval(b.interval) &&
          b.interval.lower <= b.observed &&
          b.interval.upper >= b.observed,
      )
    );
  }
  try {
    if (
      data.schema !== 'concourse-research-record-v1' ||
      !/^[a-f0-9]{64}$/.test(data.databaseSha256) ||
      data.sources.length !== 9 ||
      new Set(data.sources.map((s) => s.path)).size !== 9 ||
      data.sources.some((s) => !s.path.startsWith('outputs/') || !/^[a-f0-9]{64}$/.test(s.sha256))
    )
      return false;
    const w = data.winner;
    if (
      w.targetMet !== false ||
      !probability(w.target) ||
      !interval(w.accuracyInterval) ||
      new Set(w.forecasts.map((p) => p.id)).size !== w.forecasts.length ||
      w.seasons.length !== 5 ||
      new Set(w.seasons.map((s) => s.season)).size !== 5
    )
      return false;
    for (const row of w.seasons) {
      const ps = w.forecasts.filter((p) => p.season === row.season),
        m = row.metrics;
      if (
        !validMetrics(m) ||
        ps.length !== m.n ||
        m.correct === null ||
        ps.some(
          (p) =>
            !probability(p.probability) ||
            ![0, 1].includes(p.outcome) ||
            !p.first ||
            !p.chase ||
            p.first === p.chase ||
            !/^\d{4}-\d{2}-\d{2}$/.test(p.date) ||
            (p.latestEvidence !== null && p.latestEvidence >= p.date),
        )
      )
        return false;
      if (
        ps.filter((p) => p.probability > 0.5 === Boolean(p.outcome)).length !== m.correct ||
        !near(ps.reduce((sum, p) => sum + (p.probability - p.outcome) ** 2, 0) / m.n, m.brier)
      )
        return false;
      for (const b of m.bins) {
        const members = ps.filter(
          (p) =>
            p.probability >= b.lower &&
            (p.probability < b.upper || (b.upper === 1 && p.probability === 1)),
        );
        if (
          members.length !== b.n ||
          members.reduce((sum, p) => sum + p.outcome, 0) !== b.wins ||
          !near(members.reduce((sum, p) => sum + p.probability, 0) / b.n, b.mean)
        )
          return false;
      }
    }
    const final = w.seasons.find((s) => s.season === 2026);
    if (
      !final ||
      final.phase !== 'final' ||
      final.metrics.accuracy >= w.target ||
      !Object.values(w.baselines).every(validMetrics) ||
      Object.values(w.baselines).some((m) => m.n !== final.metrics.n)
    )
      return false;
    for (const s of data.simulator.seasons)
      for (const v of Object.values(s.variants)) {
        if (
          ![v.metrics, v.neutral, v.orderBaseline].every(validMetrics) ||
          v.metrics.n !== v.neutral.n ||
          v.metrics.n !== v.orderBaseline.n
        )
          return false;
      }
    for (const s of data.simulator.seasons)
      for (const v of Object.values(s.scores))
        for (const m of [v.raw, v.candidate]) {
          if (
            !Number.isInteger(m.n) ||
            m.n <= 0 ||
            !Number.isInteger(m.covered) ||
            !near(m.covered / m.n, m.coverage) ||
            !interval(m.interval) ||
            ![m.mae, m.width, m.intervalScore].every((n) => Number.isFinite(n) && n >= 0)
          )
            return false;
        }
    for (const s of data.delivery.seasons)
      if (
        s.raw.n !== s.corrected.n ||
        s.raw.matches !== s.corrected.matches ||
        !near(s.raw.loss - s.corrected.loss, s.gain.mean)
      )
        return false;
    return true;
  } catch {
    return false;
  }
}

export function downloadEvidence(name: string, value: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2) + '\n'], { type: 'application/json' }),
  );
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
