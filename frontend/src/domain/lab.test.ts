import { describe, expect, it } from 'vitest';
import { exampleRequest, savedRun } from '../api/simulation';
import { savedOptimizationRequest, savedOptimization, savedRosters, requestKey } from '../api/lab';
import {
  activePlayers,
  availability,
  clone,
  comparisonReady,
  initialOptimizer,
  moveBatter,
  optimizationRequest,
  optimizerIssues,
  planIssues,
  reconcilePlan,
  scenarioIssues,
  setToss,
  toggleStarter,
  type LabSlot,
} from './lab';

function slot(): LabSlot {
  return {
    request: clone(exampleRequest),
    run: clone(savedRun),
    toss: { winnerId: 'CSK', decision: 'bat' },
    names: {},
    venueName: 'Saved ground',
  };
}
const roster = savedRosters.CSK;
describe('explicit team-plan editing', () => {
  it('accepts the paired real example and the real recommended candidate', () => {
    expect(scenarioIssues(exampleRequest, savedRosters)).toEqual([]);
    expect(
      planIssues(
        savedOptimization.response.data.recommended.plan,
        roster,
        true,
        exampleRequest.as_of,
        true,
      ),
    ).toEqual([]);
  });
  it('reorders a batter without changing the XI, captain or source plan', () => {
    const p = exampleRequest.team_a,
      updated = moveBatter(p, 0, 2);
    expect(updated.batting_order[2]).toBe(p.batting_order[0]);
    expect(updated.starting_xi).toEqual(p.starting_xi);
    expect(p.batting_order[0]).toBe('23393635');
    expect(moveBatter(p, -1, 2)).toBe(p);
  });
  it('removes a starter and exposes unassigned overs rather than inventing a bowler', () => {
    const p = exampleRequest.team_a,
      id = p.bowling_plan[0],
      updated = toggleStarter(p, id, true);
    expect(updated.starting_xi).toHaveLength(10);
    expect(updated.batting_order).not.toContain(id);
    expect(updated.bowling_plan).toContain('');
    expect(planIssues(updated, roster, true, exampleRequest.as_of, true).join(' ')).toContain(
      'twenty overs',
    );
  });
  it('limits the XI and keeps substitutes distinct when promoting one', () => {
    const id = roster.members.find(
      (m) => !exampleRequest.team_a.starting_xi.includes(m.player.player_id),
    )!.player.player_id;
    expect(toggleStarter(exampleRequest.team_a, id, true)).toBe(exampleRequest.team_a);
    let p = toggleStarter(
      { ...clone(exampleRequest.team_a), substitutes: [id] },
      exampleRequest.team_a.starting_xi[0],
      true,
    );
    p = toggleStarter(p, id, true);
    expect(p.starting_xi).toContain(id);
    expect(p.substitutes).not.toContain(id);
  });
  it('derives who bats first from the hypothetical toss and decision', () => {
    expect(
      setToss(exampleRequest, { winnerId: 'CSK', decision: 'field' }).batting_first_team_id,
    ).toBe('MI');
    expect(setToss(exampleRequest, { winnerId: 'MI', decision: 'bat' }).batting_first_team_id).toBe(
      'MI',
    );
    expect(
      setToss(exampleRequest, { winnerId: 'MI', decision: 'field' }).batting_first_team_id,
    ).toBe('CSK');
  });
  it('uses the incoming Impact player only in second-innings activity', () => {
    const incoming = roster.members.find(
      (m) =>
        m.player.is_overseas === false &&
        !exampleRequest.team_a.starting_xi.includes(m.player.player_id),
    )!.player.player_id;
    const outgoing = exampleRequest.team_a.bowling_plan[0];
    const p = {
      ...clone(exampleRequest.team_a),
      substitutes: [incoming],
      impact: { outgoing_id: outgoing, incoming_id: incoming, timing: 'innings_interval' as const },
    };
    const first = reconcilePlan(p, true),
      second = reconcilePlan(p, false);
    expect(activePlayers(first, true).batting).toContain(outgoing);
    expect(first.bowling_plan).not.toContain(outgoing);
    expect(second.batting_order).toContain(incoming);
    expect(second.batting_order).not.toContain(outgoing);
    expect(second.bowling_plan).toContain(outgoing);
    expect(planIssues(first, roster, true, exampleRequest.as_of, true)).toEqual([]);
    expect(planIssues(second, roster, false, exampleRequest.as_of, true)).toEqual([]);
  });
  it('rejects overseas Impact replacements and unknown overseas classifications', () => {
    const incoming = roster.members.find(
      (m) =>
        m.player.is_overseas === true &&
        !exampleRequest.team_a.starting_xi.includes(m.player.player_id),
    )!.player.player_id;
    const p = {
      ...clone(exampleRequest.team_a),
      substitutes: [incoming],
      impact: {
        outgoing_id: exampleRequest.team_a.starting_xi[0],
        incoming_id: incoming,
        timing: 'innings_interval' as const,
      },
    };
    expect(planIssues(p, roster, true, exampleRequest.as_of, true).join(' ')).toContain('domestic');
    const unknown = clone(roster);
    unknown.members.find(
      (m) => m.player.player_id === exampleRequest.team_a.starting_xi[0],
    )!.player.is_overseas = null;
    expect(
      planIssues(exampleRequest.team_a, unknown, true, exampleRequest.as_of, true).join(' '),
    ).toContain('unknown overseas');
  });
  it('checks bowling quotas, adjacent overs and active fielding keeper', () => {
    const p = clone(exampleRequest.team_a);
    p.bowling_plan.fill(p.starting_xi[0]);
    const messages = planIssues(p, roster, true, exampleRequest.as_of, true).join(' ');
    expect(messages).toContain('four overs');
    expect(messages).toContain('consecutive');
    const noKeeper = clone(roster);
    noKeeper.members.forEach((m) => (m.player.is_wicketkeeper = false));
    expect(
      planIssues(exampleRequest.team_a, noKeeper, true, exampleRequest.as_of, true).join(' '),
    ).toContain('wicketkeeper');
  });
  it('uses availability only on the exact cutoff date; dated unavailable is never waived', () => {
    const m = clone(roster.members[0]);
    m.availability = { status: 'unavailable', effective_on: '2026-04-01' };
    expect(availability(m, '2026-04-02')).toBe('unknown');
    expect(availability(m, '2026-04-01')).toBe('unavailable');
    const dated = clone(roster);
    dated.members.find(
      (m) => m.player.player_id === exampleRequest.team_a.starting_xi[0],
    )!.availability = { status: 'unavailable', effective_on: exampleRequest.as_of };
    expect(
      planIssues(exampleRequest.team_a, dated, true, exampleRequest.as_of, true).join(' '),
    ).toContain('dated unavailable');
    expect(
      planIssues(exampleRequest.team_a, roster, true, exampleRequest.as_of, false).join(' '),
    ).toContain('Availability is unconfirmed');
  });
});
describe('optimizer boundaries and stale-result comparison', () => {
  it('builds the exact saved optimization context from default Lab settings', () => {
    expect(requestKey(optimizationRequest(exampleRequest, initialOptimizer))).toBe(
      requestKey(savedOptimizationRequest),
    );
    expect(optimizerIssues(savedOptimizationRequest, savedRosters)).toEqual([]);
  });
  it('permits an incomplete own XI because the optimizer constructs that XI', () => {
    const r = clone(exampleRequest);
    r.team_a.starting_xi = [];
    r.team_a.batting_order = [];
    r.team_a.bowling_plan = [];
    expect(optimizerIssues(optimizationRequest(r, initialOptimizer), savedRosters)).toEqual([]);
  });
  it('rejects an incomplete opponent and out-of-bound context', () => {
    const r = clone(savedOptimizationRequest);
    r.opponent.starting_xi.pop();
    expect(optimizerIssues(r, savedRosters).join(' ')).toContain('Opponent');
    expect(
      optimizerIssues({ ...savedOptimizationRequest, seed: NaN, as_of: '' }, savedRosters).length,
    ).toBeGreaterThan(0);
  });
  it('rejects conflicting locks and insufficient bowling candidates', () => {
    const id = roster.members[0].player.player_id;
    expect(
      optimizerIssues(
        { ...savedOptimizationRequest, locked_ids: [id], excluded_ids: [id] },
        savedRosters,
      ).join(' '),
    ).toContain('locked and excluded');
    const thin = clone(savedRosters);
    thin.CSK.members.forEach((m) => (m.player.primary_role = 'batter'));
    expect(optimizerIssues(savedOptimizationRequest, thin).join(' ')).toContain(
      'five eligible bowling',
    );
  });
  it('keeps copied and edited requests distinct from completed output', () => {
    const a = slot(),
      b = clone(a);
    b.run = null;
    expect(comparisonReady(a, b)).toBe(false);
    b.run = clone(savedRun);
    expect(comparisonReady(a, b)).toBe(true);
    b.request.seed = 0;
    expect(comparisonReady(a, b)).toBe(false);
    expect(a.request.seed).toBe(exampleRequest.seed);
  });
  it('requires matching teams and evidence cutoff for comparisons', () => {
    const a = slot(),
      b = slot();
    b.request.as_of = '2026-04-01';
    b.run!.request.as_of = '2026-04-01';
    expect(comparisonReady(a, b)).toBe(false);
    const other = slot();
    other.request.team_a.team_id = 'GT';
    other.run!.request.team_a.team_id = 'GT';
    expect(comparisonReady(a, other)).toBe(false);
  });
  it('requires equal trial counts, seeds and returned model/data versions', () => {
    const a = slot(),
      b = slot();
    b.request.simulations = 50;
    b.run!.request.simulations = 50;
    expect(comparisonReady(a, b)).toBe(false);
    const c = slot();
    c.run!.response.meta.dataset_version = 'different';
    expect(comparisonReady(a, c)).toBe(false);
    const d = slot();
    d.run!.response.data.simulator_version = 'different';
    expect(comparisonReady(a, d)).toBe(false);
  });
});
