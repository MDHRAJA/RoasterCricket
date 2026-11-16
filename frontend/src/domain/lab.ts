import {
  parseSimulationRequest,
  type CompletedRun,
  type SimulationRequest,
  type TeamPlan,
} from '../api/simulation';
import type { OptimizationRequest, Roster } from '../api/lab';
export type SlotId = 'A' | 'B';
export type PlanSide = 'team_a' | 'team_b';
export interface Toss {
  winnerId: string;
  decision: 'bat' | 'field';
}
export interface LabSlot {
  request: SimulationRequest;
  run: CompletedRun | null;
  toss: Toss;
  names: Record<string, string>;
  venueName: string;
}
export interface OptimizerSettings {
  side: PlanSide;
  locked: string[];
  excluded: string[];
  risk: number;
  minimumBatting: number;
  trials: number;
  candidates: number;
}
export const initialOptimizer: OptimizerSettings = {
  side: 'team_a',
  locked: [],
  excluded: [],
  risk: 1,
  minimumBatting: 6,
  trials: 200,
  candidates: 3,
};
export function clone<T>(value: T): T {
  return structuredClone(value);
}
export function activePlayers(plan: TeamPlan, battingFirst: boolean) {
  const initial = [...plan.starting_xi],
    after = initial.map((id) => (id === plan.impact?.outgoing_id ? plan.impact.incoming_id : id));
  return { batting: battingFirst ? initial : after, bowling: battingFirst ? after : initial };
}
/** Preserve order/over assignments where possible; removed players leave visible empty overs. */
export function reconcilePlan(plan: TeamPlan, battingFirst: boolean): TeamPlan {
  const active = activePlayers(plan, battingFirst),
    missing = active.batting.filter((id) => !plan.batting_order.includes(id));
  const order = plan.batting_order
    .map((id) => (active.batting.includes(id) ? id : missing.shift() || ''))
    .filter(Boolean);
  order.push(...active.batting.filter((id) => !order.includes(id)));
  return {
    ...plan,
    batting_order: order,
    bowling_plan: Array.from({ length: 20 }, (_, i) => {
      const id = plan.bowling_plan[i] || '';
      if (active.bowling.includes(id)) return id;
      const replacement =
        id === plan.impact?.outgoing_id
          ? plan.impact.incoming_id
          : id === plan.impact?.incoming_id
            ? plan.impact.outgoing_id
            : '';
      return active.bowling.includes(replacement) ? replacement : '';
    }),
  };
}
export function setToss(request: SimulationRequest, toss: Toss): SimulationRequest {
  const other = [request.team_a.team_id, request.team_b.team_id].find(
    (id) => id !== toss.winnerId,
  )!;
  const first = toss.decision === 'bat' ? toss.winnerId : other;
  return {
    ...request,
    batting_first_team_id: first,
    team_a: reconcilePlan(request.team_a, request.team_a.team_id === first),
    team_b: reconcilePlan(request.team_b, request.team_b.team_id === first),
  };
}
export function toggleStarter(plan: TeamPlan, id: string, battingFirst: boolean): TeamPlan {
  if (!plan.starting_xi.includes(id) && plan.starting_xi.length >= 11) return plan;
  const xi = plan.starting_xi.includes(id)
    ? plan.starting_xi.filter((p) => p !== id)
    : [...plan.starting_xi, id];
  const impact =
    plan.impact && xi.includes(plan.impact.outgoing_id) && !xi.includes(plan.impact.incoming_id)
      ? plan.impact
      : null;
  return reconcilePlan(
    {
      ...plan,
      starting_xi: xi,
      substitutes: plan.substitutes.filter((p) => !xi.includes(p)),
      impact,
      captain_id: xi.includes(plan.captain_id) ? plan.captain_id : xi[0] || '',
    },
    battingFirst,
  );
}
export function moveBatter(plan: TeamPlan, from: number, to: number): TeamPlan {
  if (
    from < 0 ||
    to < 0 ||
    from >= plan.batting_order.length ||
    to >= plan.batting_order.length ||
    from === to
  )
    return plan;
  const order = [...plan.batting_order],
    [id] = order.splice(from, 1);
  order.splice(to, 0, id);
  return { ...plan, batting_order: order };
}
export function availability(member: Roster['members'][number], asOf: string) {
  return member.availability.effective_on === asOf ? member.availability.status : 'unknown';
}
export function planIssues(
  plan: TeamPlan,
  roster: Roster,
  battingFirst: boolean,
  asOf: string,
  allowUnknown: boolean,
): string[] {
  const issues: string[] = [],
    byId = new Map(roster.members.map((m) => [m.player.player_id, m])),
    nominated = [...plan.starting_xi, ...plan.substitutes];
  if (plan.starting_xi.length !== 11 || new Set(plan.starting_xi).size !== 11)
    issues.push('Select eleven distinct starters.');
  if (!plan.starting_xi.includes(plan.captain_id))
    issues.push('Choose a captain from the starting XI.');
  if (
    plan.substitutes.length > 5 ||
    new Set(plan.substitutes).size !== plan.substitutes.length ||
    plan.substitutes.some((id) => plan.starting_xi.includes(id))
  )
    issues.push('Nominate up to five distinct substitutes outside the XI.');
  if (nominated.some((id) => !byId.has(id)))
    issues.push('Every nominated player must be in this saved roster.');
  if (nominated.some((id) => byId.get(id)?.player.is_overseas == null))
    issues.push('A nominated player has an unknown overseas classification.');
  if (plan.starting_xi.filter((id) => byId.get(id)?.player.is_overseas).length > 4)
    issues.push('The starting XI exceeds four overseas proxies.');
  if (nominated.some((id) => byId.has(id) && availability(byId.get(id)!, asOf) === 'unavailable'))
    issues.push('A nominated player has a dated unavailable record.');
  if (
    !allowUnknown &&
    nominated.some((id) => !byId.has(id) || availability(byId.get(id)!, asOf) !== 'available')
  )
    issues.push(
      'Availability is unconfirmed. Explicitly assume unknown availability or use dated available players.',
    );
  if (
    plan.impact &&
    (!plan.starting_xi.includes(plan.impact.outgoing_id) ||
      !plan.substitutes.includes(plan.impact.incoming_id) ||
      byId.get(plan.impact.incoming_id)?.player.is_overseas !== false)
  )
    issues.push('Impact replacement must use a starter and a domestic nominated substitute.');
  const active = activePlayers(plan, battingFirst);
  if (
    plan.batting_order.length !== 11 ||
    new Set(plan.batting_order).size !== 11 ||
    plan.batting_order.some((id) => !active.batting.includes(id))
  )
    issues.push('Batting order must contain the eleven active batting players.');
  if (
    plan.bowling_plan.length !== 20 ||
    plan.bowling_plan.some((id) => !id || !active.bowling.includes(id))
  )
    issues.push('Assign all twenty overs to active fielding players.');
  if (plan.bowling_plan.some((id) => id && plan.bowling_plan.filter((p) => p === id).length > 4))
    issues.push('A bowler has more than four overs.');
  if (plan.bowling_plan.some((id, i) => id && i > 0 && plan.bowling_plan[i - 1] === id))
    issues.push('The same bowler cannot bowl consecutive overs.');
  if (!active.bowling.some((id) => byId.get(id)?.player.is_wicketkeeper))
    issues.push('The active fielding XI needs a recorded wicketkeeper.');
  return issues;
}
export function scenarioIssues(request: SimulationRequest, rosters: Record<string, Roster>) {
  const issues: string[] = [];
  try {
    parseSimulationRequest(request);
  } catch (e) {
    issues.push(e instanceof Error ? e.message : 'Incomplete scenario.');
  }
  for (const side of ['team_a', 'team_b'] as const) {
    const p = request[side],
      r = rosters[p.team_id];
    if (!r) issues.push(`Roster unavailable: ${p.team_id}`);
    else
      issues.push(
        ...planIssues(
          p,
          r,
          p.team_id === request.batting_first_team_id,
          request.as_of,
          request.allow_unknown_availability,
        ).map((i) => `${p.team_id}: ${i}`),
      );
  }
  return [...new Set(issues)];
}
export function optimizationRequest(
  request: SimulationRequest,
  settings: OptimizerSettings,
): OptimizationRequest {
  const own = request[settings.side],
    opponent = request[settings.side === 'team_a' ? 'team_b' : 'team_a'];
  return {
    season: 2026,
    as_of: request.as_of,
    venue_id: request.venue_id,
    team_id: own.team_id,
    opponent,
    candidate_ids: null,
    locked_ids: [...settings.locked].sort(),
    excluded_ids: [...settings.excluded].sort(),
    batting_first_team_id: request.batting_first_team_id,
    allow_unknown_availability: request.allow_unknown_availability,
    minimum_batting_options: settings.minimumBatting,
    risk_aversion: settings.risk,
    use_delivery_calibration: request.use_delivery_calibration,
    candidate_count: settings.candidates,
    simulations: settings.trials,
    seed: request.seed,
  };
}
export function optimizerIssues(request: OptimizationRequest, rosters: Record<string, Roster>) {
  const issues: string[] = [],
    own = rosters[request.team_id],
    opp = rosters[request.opponent.team_id];
  if (!own || !opp) return ['Both roster snapshots are required.'];
  if (
    request.team_id === request.opponent.team_id ||
    ![request.team_id, request.opponent.team_id].includes(request.batting_first_team_id)
  )
    issues.push('Choose distinct teams and an explicit batting-first team.');
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(request.as_of) ||
    !Number.isFinite(Date.parse(request.as_of)) ||
    new Date(`${request.as_of}T00:00:00Z`).toISOString().slice(0, 10) !== request.as_of ||
    request.as_of < '2008-04-19' ||
    request.as_of > '2099-12-31'
  )
    issues.push('Use a valid exclusive evidence cutoff.');
  if (!Number.isInteger(request.seed) || request.seed < 0 || request.seed > 4294967295)
    issues.push('Use an integer seed from 0 to 4,294,967,295.');
  if (
    !Number.isInteger(request.simulations) ||
    request.simulations < 50 ||
    request.simulations > 500 ||
    !Number.isInteger(request.candidate_count) ||
    request.candidate_count < 1 ||
    request.candidate_count > 3 ||
    !Number.isFinite(request.risk_aversion) ||
    request.risk_aversion < 0 ||
    request.risk_aversion > 3 ||
    !Number.isInteger(request.minimum_batting_options) ||
    request.minimum_batting_options < 0 ||
    request.minimum_batting_options > 11
  )
    issues.push('Optimizer settings are outside the supported bounds.');
  issues.push(
    ...planIssues(
      request.opponent,
      opp,
      request.opponent.team_id === request.batting_first_team_id,
      request.as_of,
      request.allow_unknown_availability,
    ).map((i) => `Opponent: ${i}`),
  );
  if (request.locked_ids.length > 11) issues.push('Lock at most eleven players.');
  if (request.locked_ids.some((id) => request.excluded_ids.includes(id)))
    issues.push('A player cannot be locked and excluded.');
  const eligible = own.members.filter(
    (m) =>
      !request.excluded_ids.includes(m.player.player_id) &&
      m.player.is_overseas != null &&
      ['batter', 'wicketkeeper_batter', 'allrounder', 'bowler'].includes(
        m.player.primary_role || '',
      ) &&
      availability(m, request.as_of) !== 'unavailable' &&
      (request.allow_unknown_availability || availability(m, request.as_of) === 'available'),
  );
  if (eligible.length < 11) issues.push('Fewer than eleven candidates pass the planning filters.');
  if (
    eligible.filter((m) =>
      ['batter', 'wicketkeeper_batter', 'allrounder'].includes(m.player.primary_role || ''),
    ).length < request.minimum_batting_options
  )
    issues.push('The pool has too few batting-role candidates for the requested minimum.');
  if (
    request.locked_ids.filter(
      (id) => own.members.find((m) => m.player.player_id === id)?.player.is_overseas,
    ).length > 4
  )
    issues.push('Locks exceed the four-player overseas proxy quota.');
  if (
    eligible.filter((m) => ['bowler', 'allrounder'].includes(m.player.primary_role || '')).length <
    5
  )
    issues.push('At least five eligible bowling-role candidates are needed to cover twenty overs.');
  if (request.locked_ids.some((id) => !eligible.some((m) => m.player.player_id === id)))
    issues.push('A locked player does not pass the planning filters.');
  if (!eligible.some((m) => m.player.is_wicketkeeper))
    issues.push('No eligible wicketkeeper is in the candidate pool.');
  return issues;
}
export function comparisonReady(a: LabSlot, b: LabSlot) {
  return Boolean(
    a.run &&
    b.run &&
    a.request.simulations === b.request.simulations &&
    a.request.seed === b.request.seed &&
    a.run.response.meta.dataset_version === b.run.response.meta.dataset_version &&
    a.run.response.data.simulator_version === b.run.response.data.simulator_version &&
    JSON.stringify(a.request) === JSON.stringify(a.run.request) &&
    JSON.stringify(b.request) === JSON.stringify(b.run.request) &&
    a.request.as_of === b.request.as_of &&
    [a.request.team_a.team_id, a.request.team_b.team_id].sort().join('|') ===
      [b.request.team_a.team_id, b.request.team_b.team_id].sort().join('|'),
  );
}
