import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  labData,
  optimizeXI,
  parseRoster,
  requestKey,
  savedOptimization,
  savedOptimizationRequest,
  savedRosters,
  validateOptimization,
} from './lab';
const copy = <T>(v: T): T => structuredClone(v);
afterEach(() => vi.unstubAllGlobals());
describe('public Lab data contracts', () => {
  it('contains all ten team snapshots with unique player identities', () => {
    expect(Object.keys(savedRosters)).toHaveLength(10);
    for (const r of Object.values(savedRosters))
      expect(new Set(r.members.map((m) => m.player.player_id)).size).toBe(r.members.length);
    expect(labData.source_database_sha256).toMatch(/^[0-9a-f]{64}$/);
    expect(labData.optimizer_example.provenance.response_sha256).toMatch(/^[0-9a-f]{64}$/);
  });
  it('preserves unknown classifications instead of silently treating them as domestic', () => {
    const r = copy(savedRosters.CSK);
    r.members[0].player.is_overseas = null;
    expect(parseRoster(r, 'CSK').members[0].player.is_overseas).toBeNull();
    expect(() => parseRoster(r, 'MI')).toThrow('match');
    r.members.push(copy(r.members[0]));
    expect(() => parseRoster(r, 'CSK')).toThrow('Duplicate');
  });
  it('recognizes equivalent request key ordering without mutating the request', () => {
    expect(requestKey({ seed: 0, locked_ids: ['p'] })).toBe(
      requestKey({ locked_ids: ['p'], seed: 0 }),
    );
  });
});
describe('optimizer response integrity', () => {
  it('validates the real saved candidate, alternatives and independent confirmation', () => {
    const r = validateOptimization(savedOptimization.response, savedOptimizationRequest);
    expect(r.data.confirmation.seed).toBe((savedOptimizationRequest.seed ^ 0xa5a5a5a5) >>> 0);
    expect(r.data.objective.global_win_probability_optimality_proven).toBe(false);
  });
  it('rejects confirmation results from a different request', () => {
    const r = copy(savedOptimization.response);
    r.data.confirmation.seed = 0;
    expect(() => validateOptimization(r, savedOptimizationRequest)).toThrow();
    expect(() =>
      validateOptimization(savedOptimization.response, {
        ...savedOptimizationRequest,
        simulations: 50,
      }),
    ).toThrow();
  });
  it('rejects malformed outcome counts and illegal returned bowling assignments', () => {
    const r = copy(savedOptimization.response);
    r.data.recommended.simulation.count++;
    expect(() => validateOptimization(r, savedOptimizationRequest)).toThrow();
    const b = copy(savedOptimization.response);
    b.data.recommended.plan.bowling_plan.fill(b.data.recommended.plan.starting_xi[0]);
    expect(() => validateOptimization(b, savedOptimizationRequest)).toThrow();
  });
  it('enforces requested locks and exclusions against a returned candidate', () => {
    const excluded = savedOptimization.response.data.recommended.plan.starting_xi[0];
    expect(() =>
      validateOptimization(savedOptimization.response, {
        ...savedOptimizationRequest,
        excluded_ids: [excluded],
      }),
    ).toThrow();
    const r = copy(savedOptimization.response);
    r.data.constraints.locked_ids = ['not-in-xi'];
    expect(() =>
      validateOptimization(r, { ...savedOptimizationRequest, locked_ids: ['not-in-xi'] }),
    ).toThrow();
  });
  it('rejects duplicate candidate XIs', () => {
    const r = copy(savedOptimization.response);
    r.data.alternatives[0] = copy(r.data.recommended);
    expect(() => validateOptimization(r, savedOptimizationRequest)).toThrow();
  });
});
describe('optimizer computation endpoint', () => {
  it('posts the full bounded request and propagates the cancellation signal', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => savedOptimization.response }),
    );
    const signal = new AbortController().signal;
    await optimizeXI(savedOptimizationRequest, signal);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/optimization/xi'),
      expect.objectContaining({
        signal,
        method: 'POST',
        body: JSON.stringify(savedOptimizationRequest),
      }),
    );
  });
  it('reports infeasible pools and occupied slots rather than returning the saved candidate', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          error: { code: 'no_feasible_xi', message: 'No XI satisfies constraints' },
        }),
      }),
    );
    await expect(
      optimizeXI(savedOptimizationRequest, new AbortController().signal),
    ).rejects.toThrow('No XI');
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 429,
        json: async () => ({ error: { code: 'busy' } }),
      }),
    );
    await expect(
      optimizeXI(savedOptimizationRequest, new AbortController().signal),
    ).rejects.toThrow('Another planning');
  });
  it('reports a missing backend without substituting a mock result', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')));
    await expect(
      optimizeXI(savedOptimizationRequest, new AbortController().signal),
    ).rejects.toThrow('unavailable');
  });
});
