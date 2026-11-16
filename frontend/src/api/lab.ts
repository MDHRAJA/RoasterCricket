import bundle from './snapshots/lab.json';
import type { Envelope } from './contracts';
import {
  parseSimulationRequest,
  SimulationError,
  type Outcome,
  type SimulationRequest,
  type TeamPlan,
} from './simulation';

export interface PlayerProfile {
  player_id: string;
  display_name: string;
  country: string | null;
  primary_role: string | null;
  is_wicketkeeper: boolean | null;
  is_overseas: boolean | null;
}
export interface RosterMember {
  player: PlayerProfile;
  availability: { status: string; effective_on: string | null };
}
export interface Roster {
  team_id: string;
  members: RosterMember[];
  warnings: string[];
}
export interface Ground {
  venue_id: string;
  display_name: string;
  city: string | null;
}
export interface OptimizationRequest {
  season: 2026;
  as_of: string;
  venue_id: string;
  team_id: string;
  opponent: TeamPlan;
  batting_first_team_id: string;
  candidate_ids: string[] | null;
  locked_ids: string[];
  excluded_ids: string[];
  allow_unknown_availability: boolean;
  minimum_batting_options: number;
  risk_aversion: number;
  use_delivery_calibration: boolean;
  candidate_count: number;
  simulations: number;
  seed: number;
}
export interface OptimizedCandidate {
  candidate_rank_by_proxy: number;
  plan: TeamPlan;
  proxy_score: number;
  proxy_optimality_proven: boolean;
  relative_mip_gap: number | null;
  simulation: Outcome;
}
export interface OptimizationResult {
  optimizer_version: string;
  status: string;
  eligibility_verified: boolean;
  objective: {
    risk_aversion: number;
    global_win_probability_optimality_proven: boolean;
    batting_order: string;
    captain: string;
    impact_optimized: boolean;
  };
  recommended: OptimizedCandidate;
  alternatives: OptimizedCandidate[];
  exclusions: { player_id: string; reason: string }[];
  constraints: {
    xi_size: number;
    max_overseas_proxy: number;
    min_keeper: number;
    minimum_batting_options: number;
    max_overs_per_bowler: number;
    consecutive_overs_forbidden: boolean;
    locked_ids: string[];
    availability_assumed: boolean;
  };
  confirmation: {
    seed: number;
    simulations: number;
    selected_team_outcome: Outcome;
    training: {
      exclusive_cutoff: string;
      last_included_date: string | null;
      [key: string]: unknown;
    };
    interpretation: string;
  };
  reliability: { selection_basis?: string; [key: string]: unknown };
}
export interface OptimizationRun {
  request: OptimizationRequest;
  response: Envelope<OptimizationResult>;
  source: 'saved' | 'api';
  completedAt: string | null;
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('The service returned an incomplete response.');
  return value as Record<string, unknown>;
}
function bool(value: unknown) {
  if (value === null || value === undefined) return null;
  if (![true, false, 0, 1].includes(value as boolean))
    throw new Error('Unsupported roster classification.');
  return Boolean(value);
}
export function parseRoster(value: unknown, teamId: string): Roster {
  const r = record(value);
  if (
    r.team_id !== teamId ||
    !Array.isArray(r.members) ||
    !r.members.length ||
    r.members.length > 60
  )
    throw new Error('Roster response does not match this team.');
  const members = r.members.map((raw) => {
    const m = record(raw),
      p = record(m.player),
      a = record(m.availability);
    if (
      typeof p.player_id !== 'string' ||
      typeof p.display_name !== 'string' ||
      (p.primary_role != null && typeof p.primary_role !== 'string') ||
      typeof a.status !== 'string' ||
      (a.effective_on != null && typeof a.effective_on !== 'string')
    )
      throw new Error('Incomplete roster member.');
    return {
      player: {
        player_id: p.player_id,
        display_name: p.display_name,
        country: typeof p.country === 'string' ? p.country : null,
        primary_role: typeof p.primary_role === 'string' ? p.primary_role : null,
        is_wicketkeeper: bool(p.is_wicketkeeper),
        is_overseas: bool(p.is_overseas),
      },
      availability: {
        status: a.status,
        effective_on: typeof a.effective_on === 'string' ? a.effective_on : null,
      },
    };
  });
  if (new Set(members.map((m) => m.player.player_id)).size !== members.length)
    throw new Error('Duplicate roster players.');
  return {
    team_id: teamId,
    members,
    warnings: Array.isArray(r.warnings)
      ? r.warnings.filter((w): w is string => typeof w === 'string')
      : [],
  };
}
export const labData = bundle;
export const savedRosters: Record<string, Roster> = Object.fromEntries(
  Object.entries(bundle.rosters).map(([id, roster]) => [id, parseRoster(roster, id)]),
);
export const grounds: Ground[] = bundle.venues;
export function normalizeOptimization(
  r: Partial<OptimizationRequest> &
    Pick<
      OptimizationRequest,
      'team_id' | 'opponent' | 'venue_id' | 'as_of' | 'batting_first_team_id'
    >,
): OptimizationRequest {
  return {
    season: 2026,
    as_of: r.as_of,
    venue_id: r.venue_id,
    team_id: r.team_id,
    opponent: r.opponent,
    batting_first_team_id: r.batting_first_team_id,
    candidate_ids: r.candidate_ids ?? null,
    locked_ids: [...(r.locked_ids ?? [])].sort(),
    excluded_ids: [...(r.excluded_ids ?? [])].sort(),
    allow_unknown_availability: r.allow_unknown_availability ?? false,
    minimum_batting_options: r.minimum_batting_options ?? 6,
    risk_aversion: r.risk_aversion ?? 1,
    use_delivery_calibration: r.use_delivery_calibration ?? false,
    candidate_count: r.candidate_count ?? 3,
    simulations: r.simulations ?? 200,
    seed: r.seed ?? 20261002,
  };
}
export function requestKey(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(requestKey).join(',')}]`;
  if (value && typeof value === 'object')
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([k, v]) => `${JSON.stringify(k)}:${requestKey(v)}`)
      .join(',')}}`;
  return JSON.stringify(value);
}
function validOutcome(raw: unknown, n: number): raw is Outcome {
  const o = record(raw),
    i = record(o.sampling_interval);
  return (
    Number.isInteger(o.count) &&
    Number(o.count) >= 0 &&
    Number(o.count) <= n &&
    typeof o.probability === 'number' &&
    Number.isFinite(o.probability) &&
    Math.abs(o.probability - Number(o.count) / n) < 1e-8 &&
    i.level === 0.95 &&
    typeof i.lower === 'number' &&
    typeof i.upper === 'number' &&
    i.lower >= 0 &&
    i.upper <= 1 &&
    i.lower <= o.probability + 1e-9 &&
    i.upper >= o.probability - 1e-9
  );
}
export function validateOptimization(
  value: unknown,
  request: OptimizationRequest,
): Envelope<OptimizationResult> {
  const e = record(value),
    d = record(e.data),
    meta = record(e.meta),
    confirmation = record(d.confirmation),
    training = record(confirmation.training),
    objective = record(d.objective),
    constraints = record(d.constraints);
  const fail = () => {
    throw new Error('Optimizer output does not match the submitted request.');
  };
  if (
    typeof d.optimizer_version !== 'string' ||
    d.status !== 'experimental_planning' ||
    typeof d.eligibility_verified !== 'boolean' ||
    meta.before !== request.as_of ||
    typeof meta.dataset_version !== 'string' ||
    !Array.isArray(meta.warnings) ||
    !meta.warnings.every((w) => typeof w === 'string') ||
    !Array.isArray(d.alternatives) ||
    d.alternatives.length >= request.candidate_count ||
    !Array.isArray(d.exclusions) ||
    !d.exclusions.every(
      (v) => typeof record(v).player_id === 'string' && typeof record(v).reason === 'string',
    )
  )
    fail();
  if (
    confirmation.simulations !== request.simulations ||
    confirmation.seed !== (request.seed ^ 0xa5a5a5a5) >>> 0 ||
    training.exclusive_cutoff !== request.as_of ||
    !validOutcome(confirmation.selected_team_outcome, request.simulations) ||
    objective.risk_aversion !== request.risk_aversion ||
    objective.global_win_probability_optimality_proven !== false ||
    constraints.xi_size !== 11 ||
    constraints.minimum_batting_options !== request.minimum_batting_options ||
    constraints.availability_assumed !== request.allow_unknown_availability ||
    requestKey([...((constraints.locked_ids as string[]) || [])].sort()) !==
      requestKey([...request.locked_ids].sort())
  )
    fail();
  record(d.reliability);
  const candidates = [d.recommended, ...(d.alternatives as unknown[])];
  const seen = new Set<string>();
  for (const raw of candidates) {
    const c = record(raw),
      p = record(c.plan);
    if (
      p.team_id !== request.team_id ||
      typeof c.proxy_score !== 'number' ||
      !Number.isFinite(c.proxy_score) ||
      typeof c.proxy_optimality_proven !== 'boolean' ||
      !validOutcome(c.simulation, request.simulations)
    )
      fail();
    const context: SimulationRequest = {
      season: 2026,
      as_of: request.as_of,
      venue_id: request.venue_id,
      team_a: p as unknown as TeamPlan,
      team_b: request.opponent,
      batting_first_team_id: request.batting_first_team_id,
      simulations: request.simulations,
      seed: request.seed,
      sample_posterior: true,
      use_delivery_calibration: request.use_delivery_calibration,
      include_sample_match: false,
      allow_unknown_availability: request.allow_unknown_availability,
      max_super_overs: 6,
    };
    const plan = parseSimulationRequest(context).team_a;
    if (
      request.locked_ids.some((id) => !plan.starting_xi.includes(id)) ||
      request.excluded_ids.some((id) => plan.starting_xi.includes(id)) ||
      (request.candidate_ids && plan.starting_xi.some((id) => !request.candidate_ids!.includes(id)))
    )
      fail();
    const key = [...plan.starting_xi].sort().join('|');
    if (seen.has(key)) fail();
    seen.add(key);
    if (
      plan.bowling_plan.some((id, index) => index > 0 && plan.bowling_plan[index - 1] === id) ||
      plan.bowling_plan.some(
        (id) =>
          !plan.starting_xi.includes(id) || plan.bowling_plan.filter((p) => p === id).length > 4,
      ) ||
      plan.batting_order.some((id) => !plan.starting_xi.includes(id))
    )
      fail();
  }
  return value as Envelope<OptimizationResult>;
}
export const savedOptimizationRequest = normalizeOptimization(
  bundle.optimizer_example.request as OptimizationRequest,
);
export const savedOptimization: OptimizationRun = {
  request: savedOptimizationRequest,
  response: validateOptimization(bundle.optimizer_example.response, savedOptimizationRequest),
  source: 'saved',
  completedAt: null,
};

const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');
export async function fetchRoster(id: string, signal: AbortSignal) {
  const response = await fetch(`${base}/teams/${encodeURIComponent(id)}/roster?season=2026`, {
    signal,
  });
  if (!response.ok) throw new Error('Roster unavailable');
  const body = record(await response.json()),
    data = record(body.data),
    team = record(data.team);
  if (data.season !== 2026) throw new Error('Wrong roster season');
  return parseRoster(
    { team_id: team.team_id, members: data.members, warnings: record(body.meta).warnings },
    id,
  );
}
export async function optimizeXI(request: OptimizationRequest, signal: AbortSignal) {
  let response: Response;
  try {
    response = await fetch(`${base}/optimization/xi`, {
      method: 'POST',
      headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal,
    });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new SimulationError('The optimizer is unavailable. Start the local backend, then retry.');
  }
  let value: unknown;
  try {
    value = await response.json();
  } catch {
    throw new SimulationError(
      'The optimizer did not return a usable response. Check the backend connection.',
    );
  }
  if (!response.ok) {
    const error = record(record(value).error);
    throw new SimulationError(
      response.status === 429
        ? 'Another planning job is running. Wait for it to finish, then retry.'
        : typeof error.message === 'string'
          ? error.message
          : 'The optimizer could not complete.',
      String(error.code || response.status),
    );
  }
  return validateOptimization(value, request);
}
