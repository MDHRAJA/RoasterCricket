import type { Envelope } from './contracts';
import saved from './snapshots/scenario-csk-mi.json';

export interface TeamPlan {
  team_id: string;
  starting_xi: string[];
  batting_order: string[];
  bowling_plan: string[];
  captain_id: string;
  substitutes: string[];
  impact: { outgoing_id: string; incoming_id: string; timing: 'innings_interval' } | null;
}
export interface SimulationRequest {
  season: 2026;
  as_of: string;
  venue_id: string;
  team_a: TeamPlan;
  team_b: TeamPlan;
  batting_first_team_id: string;
  simulations: number;
  seed: number;
  sample_posterior: boolean;
  use_delivery_calibration: boolean;
  include_sample_match: boolean;
  allow_unknown_availability: boolean;
  max_super_overs: number;
}
export interface Outcome {
  count: number;
  probability: number;
  sampling_interval: { level: number; lower: number; upper: number; interpretation: string };
}
export interface ScoreBin {
  lower: number;
  upper_exclusive: number;
  count: number;
}
export interface InningsSummary {
  team_id: string;
  mean_runs: number;
  score_quantiles: { p05: number; p10: number; p50: number; p90: number; p95: number };
  score_standard_deviation: number;
  mean_runs_mc_standard_error: number;
  mean_wickets: number;
  mean_legal_balls: number;
  score_histogram: ScoreBin[];
}
export interface Delivery {
  physical_delivery: number;
  legal_balls_before: number;
  striker_id: string;
  non_striker_id: string;
  bowler_id: string;
  kind: 'legal' | 'wide' | 'noball';
  batter_runs: number;
  extras: number;
  dismissed_id: string | null;
  score: number;
  wickets: number;
  free_hit_next: boolean;
}
export interface SampleInnings {
  team_id: string;
  runs: number;
  wickets: number;
  legal_balls: number;
  termination: string;
  extras: Record<string, number>;
  batting: {
    player_id: string;
    runs: number;
    balls_faced: number;
    dismissed: boolean;
    entered: boolean;
  }[];
  bowling: { player_id: string; legal_balls: number; runs_conceded: number; wickets: number }[];
  deliveries?: Delivery[];
}
export interface SimulationResult {
  simulator_version: string;
  status: string;
  eligibility_verified: boolean;
  simulations: number;
  seed: number;
  outcomes: Record<string, Outcome | number> & {
    regular_tie_probability: number;
    super_over_probability: number;
  };
  innings: InningsSummary[];
  training: {
    exclusive_cutoff: string;
    first_included_date: string | null;
    last_included_date: string | null;
    recorded_deliveries: number;
    legal_deliveries: number;
    delivery_calibration: string;
    posterior_sampling: boolean;
    max_super_overs: number;
    rules_profile: string;
    window_start: string;
  };
  reliability: {
    status?: string;
    match_level_calibrated?: boolean;
    decision_ready?: boolean;
    flags?: string[];
    evidence?: {
      simulated_legal_delivery_exposures?: {
        legal_delivery_draws: number;
        no_direct_history_fraction: number;
      };
    };
  };
  assumptions: string[];
  sample_match: {
    innings: SampleInnings[];
    winner_id: string | null;
    super_overs: unknown[];
  } | null;
}
export interface CompletedRun {
  request: SimulationRequest;
  response: Envelope<SimulationResult>;
  source: 'saved' | 'api';
  completedAt: string | null;
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('Expected an object.');
  return value as Record<string, unknown>;
}
function text(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= 100;
}
function integer(value: unknown, min: number, max: number): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value >= min && value <= max;
}
function finite(value: unknown, min = 0, max = 1e7): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max;
}
function allowed(row: Record<string, unknown>, keys: string[]) {
  if (Object.keys(row).some((k) => !keys.includes(k)))
    throw new Error('The request contains an unsupported field.');
}
function plan(value: unknown): TeamPlan {
  const p = object(value);
  allowed(p, [
    'team_id',
    'starting_xi',
    'batting_order',
    'bowling_plan',
    'captain_id',
    'substitutes',
    'impact',
  ]);
  if (!text(p.team_id) || !text(p.captain_id))
    throw new Error('Each plan needs a team and captain.');
  for (const [key, size] of [
    ['starting_xi', 11],
    ['batting_order', 11],
    ['bowling_plan', 20],
  ] as const) {
    if (!Array.isArray(p[key]) || p[key].length !== size || !p[key].every(text))
      throw new Error(`Each ${key.replaceAll('_', ' ')} needs ${size} player IDs.`);
  }
  const xi = p.starting_xi as string[],
    order = p.batting_order as string[];
  const substitutes = p.substitutes ?? [];
  if (new Set(xi).size !== 11 || new Set(order).size !== 11 || !xi.includes(p.captain_id))
    throw new Error('Use eleven distinct players and a captain in the XI.');
  if (
    !Array.isArray(substitutes) ||
    substitutes.length > 5 ||
    !substitutes.every(text) ||
    new Set(substitutes).size !== substitutes.length ||
    substitutes.some((id) => xi.includes(id))
  )
    throw new Error('Substitutes must be distinct from the XI, with at most five players.');
  let impact: TeamPlan['impact'] = null;
  if (p.impact != null) {
    const i = object(p.impact);
    allowed(i, ['outgoing_id', 'incoming_id', 'timing']);
    if (
      !text(i.outgoing_id) ||
      !text(i.incoming_id) ||
      (i.timing != null && i.timing !== 'innings_interval')
    )
      throw new Error('Only explicit innings-interval Impact plans are supported.');
    impact = { outgoing_id: i.outgoing_id, incoming_id: i.incoming_id, timing: 'innings_interval' };
  }
  return {
    team_id: p.team_id,
    starting_xi: xi,
    batting_order: order,
    bowling_plan: p.bowling_plan as string[],
    captain_id: p.captain_id,
    substitutes,
    impact,
  };
}

/** Structural validation only; the backend remains authoritative for roster/rule checks. */
export function parseSimulationRequest(value: unknown): SimulationRequest {
  const r = object(value);
  allowed(r, [
    'season',
    'as_of',
    'venue_id',
    'team_a',
    'team_b',
    'batting_first_team_id',
    'simulations',
    'seed',
    'sample_posterior',
    'use_delivery_calibration',
    'include_sample_match',
    'allow_unknown_availability',
    'max_super_overs',
  ]);
  if ((r.season ?? 2026) !== 2026)
    throw new Error('Simulation currently supports the 2026 planning profile only.');
  if (
    !text(r.as_of) ||
    !/^\d{4}-\d{2}-\d{2}$/.test(r.as_of) ||
    !Number.isFinite(Date.parse(r.as_of)) ||
    new Date(`${r.as_of}T00:00:00Z`).toISOString().slice(0, 10) !== r.as_of ||
    r.as_of < '2008-04-19' ||
    r.as_of > '2099-12-31' ||
    !text(r.venue_id)
  )
    throw new Error('Use a valid exclusive cutoff date and venue ID.');
  const a = plan(r.team_a),
    b = plan(r.team_b);
  if (a.team_id === b.team_id || ![a.team_id, b.team_id].includes(String(r.batting_first_team_id)))
    throw new Error('Choose two different teams and an explicit batting-first team.');
  if (
    [...a.starting_xi, ...a.substitutes].some((id) =>
      [...b.starting_xi, ...b.substitutes].includes(id),
    )
  )
    throw new Error('A player cannot appear in both teams.');
  const simulations = r.simulations ?? 500,
    seed = r.seed ?? 20261002,
    max = r.max_super_overs ?? 6;
  if (!integer(simulations, 50, 1000) || !integer(seed, 0, 4294967295) || !integer(max, 0, 6))
    throw new Error(
      'Use 50–1,000 trials, a seed from 0 to 4,294,967,295 and at most six Super Overs.',
    );
  for (const key of [
    'sample_posterior',
    'use_delivery_calibration',
    'include_sample_match',
    'allow_unknown_availability',
  ])
    if (r[key] != null && typeof r[key] !== 'boolean')
      throw new Error(`${key} must be true or false.`);
  return {
    season: 2026,
    as_of: r.as_of,
    venue_id: r.venue_id,
    team_a: a,
    team_b: b,
    batting_first_team_id: String(r.batting_first_team_id),
    simulations,
    seed,
    sample_posterior: (r.sample_posterior ?? true) as boolean,
    use_delivery_calibration: (r.use_delivery_calibration ?? false) as boolean,
    include_sample_match: (r.include_sample_match ?? false) as boolean,
    allow_unknown_availability: (r.allow_unknown_availability ?? false) as boolean,
    max_super_overs: max,
  };
}

export function validateSimulationResponse(
  value: unknown,
  request: SimulationRequest,
): Envelope<SimulationResult> {
  const fail = () => {
    throw new Error('The simulation response is incomplete or does not match this request.');
  };
  const envelope = object(value),
    d = object(envelope.data),
    meta = object(envelope.meta);
  const outcomes = object(d.outcomes),
    training = object(d.training);
  const reliability = object(d.reliability);
  if (reliability.evidence != null) {
    const evidence = object(reliability.evidence);
    if (evidence.simulated_legal_delivery_exposures != null) {
      const exposures = object(evidence.simulated_legal_delivery_exposures);
      if (
        !finite(exposures.no_direct_history_fraction, 0, 1) ||
        !integer(exposures.legal_delivery_draws, 0, 1e8)
      )
        fail();
    }
  }
  if (
    d.simulations !== request.simulations ||
    d.seed !== request.seed ||
    training.exclusive_cutoff !== request.as_of ||
    meta.before !== request.as_of ||
    typeof d.simulator_version !== 'string' ||
    typeof d.status !== 'string' ||
    typeof d.eligibility_verified !== 'boolean' ||
    !Array.isArray(d.assumptions) ||
    !d.assumptions.every((x) => typeof x === 'string') ||
    !Array.isArray(meta.warnings) ||
    !meta.warnings.every((x) => typeof x === 'string')
  )
    fail();
  let total = 0;
  for (const id of [request.team_a.team_id, request.team_b.team_id, 'unresolved_tie']) {
    const o = object(outcomes[id]),
      interval = object(o.sampling_interval);
    if (
      !integer(o.count, 0, request.simulations) ||
      !finite(o.probability, 0, 1) ||
      Math.abs(Number(o.probability) - Number(o.count) / request.simulations) > 1e-8 ||
      !finite(interval.lower, 0, 1) ||
      !finite(interval.upper, 0, 1) ||
      Number(interval.lower) > Number(interval.upper) ||
      !finite(interval.level, 0, 1) ||
      Math.abs(Number(interval.level) - 0.95) > 1e-9
    )
      fail();
    total += Number(o.count);
  }
  if (
    total !== request.simulations ||
    !finite(outcomes.regular_tie_probability, 0, 1) ||
    !finite(outcomes.super_over_probability, 0, 1)
  )
    fail();
  if (!Array.isArray(d.innings) || d.innings.length !== 2) fail();
  const summaries = d.innings as unknown[];
  if (new Set(summaries.map((i) => object(i).team_id)).size !== 2) fail();
  for (const entry of summaries) {
    const i = object(entry),
      q = object(i.score_quantiles);
    if (
      ![request.team_a.team_id, request.team_b.team_id].includes(String(i.team_id)) ||
      ![
        'mean_runs',
        'mean_wickets',
        'mean_legal_balls',
        'score_standard_deviation',
        'mean_runs_mc_standard_error',
      ].every((k) => finite(i[k])) ||
      !['p05', 'p10', 'p50', 'p90', 'p95'].every((k) => finite(q[k])) ||
      !Array.isArray(i.score_histogram) ||
      !i.score_histogram.length
    )
      fail();
    const bins = i.score_histogram as unknown[];
    const quantiles = ['p05', 'p10', 'p50', 'p90', 'p95'].map((key) => Number(q[key]));
    if (quantiles.some((v, index) => index > 0 && v < quantiles[index - 1])) fail();
    let count = 0,
      end = -1;
    for (const entry of bins) {
      const bin = object(entry);
      if (
        !integer(bin.lower, 0, 10000) ||
        !integer(bin.upper_exclusive, 1, 10010) ||
        Number(bin.upper_exclusive) - Number(bin.lower) !== 10 ||
        Number(bin.lower) < end ||
        !integer(bin.count, 0, request.simulations)
      )
        fail();
      end = Number(bin.upper_exclusive);
      count += Number(bin.count);
    }
    if (count !== request.simulations) fail();
  }
  if (
    training.last_included_date != null &&
    (typeof training.last_included_date !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}$/.test(training.last_included_date) ||
      !Number.isFinite(Date.parse(training.last_included_date)))
  )
    fail();
  if (
    !['recorded_deliveries', 'legal_deliveries'].every((k) => finite(training[k])) ||
    typeof training.delivery_calibration !== 'string' ||
    training.posterior_sampling !== request.sample_posterior ||
    training.max_super_overs !== request.max_super_overs ||
    typeof meta.dataset_version !== 'string'
  )
    fail();
  if (d.sample_match != null) validateSample(d.sample_match, request, fail);
  if (request.include_sample_match && d.sample_match == null) fail();
  return value as Envelope<SimulationResult>;
}

function validateSample(value: unknown, request: SimulationRequest, fail: () => never) {
  const sample = object(value);
  if (
    !Array.isArray(sample.innings) ||
    sample.innings.length !== 2 ||
    !Array.isArray(sample.super_overs)
  )
    fail();
  if (
    new Set((sample.innings as unknown[]).map((i) => object(i).team_id)).size !== 2 ||
    (sample.winner_id !== null &&
      ![request.team_a.team_id, request.team_b.team_id].includes(String(sample.winner_id)))
  )
    fail();
  for (const raw of sample.innings as unknown[]) {
    const i = object(raw);
    if (
      ![request.team_a.team_id, request.team_b.team_id].includes(String(i.team_id)) ||
      !integer(i.runs, 0, 10000) ||
      !integer(i.wickets, 0, 10) ||
      !integer(i.legal_balls, 0, 120) ||
      !Array.isArray(i.batting) ||
      !Array.isArray(i.bowling)
    )
      fail();
    for (const raw of i.batting as unknown[]) {
      const p = object(raw);
      if (
        !text(p.player_id) ||
        !integer(p.runs, 0, 10000) ||
        !integer(p.balls_faced, 0, 20000) ||
        typeof p.entered !== 'boolean' ||
        typeof p.dismissed !== 'boolean'
      )
        fail();
    }
    for (const raw of i.bowling as unknown[]) {
      const p = object(raw);
      if (
        !text(p.player_id) ||
        !integer(p.legal_balls, 0, 120) ||
        !integer(p.runs_conceded, 0, 10000) ||
        !integer(p.wickets, 0, 10)
      )
        fail();
    }
    const extras = object(i.extras);
    if (!Object.values(extras).every((x) => integer(x, 0, 10000))) fail();
    if (
      (i.batting as unknown[]).reduce<number>((sum, p) => sum + Number(object(p).runs), 0) +
        Object.values(extras).reduce<number>((sum, n) => sum + Number(n), 0) !==
      i.runs
    )
      fail();
    if (i.deliveries != null) {
      if (!Array.isArray(i.deliveries)) fail();
      let previousLegal = 0;
      for (const raw of i.deliveries as unknown[]) {
        const e = object(raw);
        if (
          !integer(e.legal_balls_before, 0, 120) ||
          Number(e.legal_balls_before) < previousLegal ||
          !integer(e.score, 0, 10000) ||
          !integer(e.wickets, 0, 10) ||
          !integer(e.batter_runs, 0, 100) ||
          !integer(e.extras, 0, 100) ||
          !integer(e.physical_delivery, 1, 20000) ||
          !['legal', 'wide', 'noball'].includes(String(e.kind)) ||
          !text(e.striker_id) ||
          !text(e.bowler_id) ||
          (e.dismissed_id !== null && !text(e.dismissed_id))
        )
          fail();
        previousLegal = Number(e.legal_balls_before);
      }
      const last = object((i.deliveries as unknown[]).at(-1));
      if (
        last.score !== i.runs ||
        last.wickets !== i.wickets ||
        Number(last.legal_balls_before) + Number(last.kind === 'legal') !== i.legal_balls
      )
        fail();
    }
  }
}

export const savedScenario = saved;
export const exampleRequest = parseSimulationRequest(saved.request);
export const savedRun: CompletedRun = {
  request: exampleRequest,
  response: validateSimulationResponse(saved.response, exampleRequest),
  source: 'saved',
  completedAt: null,
};
export function outcome(result: SimulationResult, id: string): Outcome {
  return result.outcomes[id] as Outcome;
}

export class SimulationError extends Error {
  constructor(
    message: string,
    public code = 'connection',
    public details: string[] = [],
  ) {
    super(message);
  }
}
export async function runSimulation(
  request: SimulationRequest,
  signal: AbortSignal,
): Promise<Envelope<SimulationResult>> {
  const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');
  let response: Response;
  try {
    response = await fetch(`${base}/simulations/match`, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal,
    });
  } catch (e) {
    if (signal.aborted) throw e;
    throw new SimulationError(
      'The simulation service is unavailable. Start the local backend, then retry.',
    );
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new SimulationError(
      'The simulation service did not return a usable response. Check the backend connection.',
    );
  }
  if (!response.ok) {
    const error = object(object(body).error);
    const details = Array.isArray(error.details)
      ? error.details.map((v) => {
          const d = object(v);
          return `${Array.isArray(d.location) ? d.location.slice(1).join(' / ') : 'Request'}: ${String(d.message)}`;
        })
      : [];
    throw new SimulationError(
      response.status === 429
        ? 'Another planning run is in progress. Wait for it to finish, then retry.'
        : typeof error.message === 'string'
          ? error.message
          : 'The simulation could not complete.',
      String(error.code || response.status),
      details,
    );
  }
  return validateSimulationResponse(body, request);
}
