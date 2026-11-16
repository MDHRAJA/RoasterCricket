import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  exampleRequest,
  parseSimulationRequest,
  runSimulation,
  savedRun,
  savedScenario,
  validateSimulationResponse,
} from './simulation';

const copy = <T>(value: T): T => JSON.parse(JSON.stringify(value));
afterEach(() => vi.unstubAllGlobals());
describe('explicit simulation requests', () => {
  it('normalizes the saved request with backend defaults', () => {
    expect(exampleRequest.seed).toBe(20261002);
    expect(exampleRequest.simulations).toBe(200);
    expect(exampleRequest.sample_posterior).toBe(true);
    expect(exampleRequest.use_delivery_calibration).toBe(false);
  });
  it.each([49, 1001, NaN, 200.5])('rejects invalid trial count %s', (simulations) =>
    expect(() => parseSimulationRequest({ ...exampleRequest, simulations })).toThrow('50–1,000'),
  );
  it.each([-1, 4294967296, 1.5])('rejects invalid seed %s', (seed) =>
    expect(() => parseSimulationRequest({ ...exampleRequest, seed })).toThrow(),
  );
  it('accepts zero as a valid seed', () =>
    expect(parseSimulationRequest({ ...exampleRequest, seed: 0 }).seed).toBe(0));
  it('rejects unsupported season, invalid date and unknown controls', () => {
    expect(() => parseSimulationRequest({ ...exampleRequest, season: 2025 })).toThrow('2026');
    expect(() => parseSimulationRequest({ ...exampleRequest, as_of: '2026-02-30' })).toThrow(
      'date',
    );
    expect(() => parseSimulationRequest({ ...exampleRequest, dew: 1 })).toThrow('unsupported');
  });
  it('rejects duplicate XIs and cross-team nominations', () => {
    const r = copy(exampleRequest);
    r.team_a.starting_xi[1] = r.team_a.starting_xi[0];
    expect(() => parseSimulationRequest(r)).toThrow('distinct');
    const b = copy(exampleRequest);
    b.team_b.starting_xi[0] = b.team_a.starting_xi[0];
    b.team_b.captain_id = b.team_b.starting_xi[0];
    expect(() => parseSimulationRequest(b)).toThrow('both teams');
  });
});
describe('completed run integrity', () => {
  it('checks the real saved run against its paired inputs', () => {
    expect(
      validateSimulationResponse(savedScenario.response, exampleRequest).data.simulations,
    ).toBe(200);
    expect(savedScenario.provenance.response_sha256).toMatch(/^[a-f0-9]{64}$/);
    expect(savedRun.response.data.outcomes.unresolved_tie).toHaveProperty('count', 0);
  });
  it('rejects stale results for a different seed, trial count or cutoff', () => {
    for (const change of [{ seed: 2 }, { simulations: 50 }, { as_of: '2026-04-01' }])
      expect(() =>
        validateSimulationResponse(savedScenario.response, { ...exampleRequest, ...change }),
      ).toThrow('does not match');
  });
  it('rejects outcome counts that do not reconcile to the run', () => {
    const r = copy(savedScenario.response);
    r.data.outcomes.CSK.count++;
    expect(() => validateSimulationResponse(r, exampleRequest)).toThrow();
  });
  it('rejects dropped histogram bins and nonfinite estimates', () => {
    const r = copy(savedScenario.response);
    r.data.innings[0].score_histogram.pop();
    expect(() => validateSimulationResponse(r, exampleRequest)).toThrow();
    const n = copy(savedScenario.response);
    n.data.innings[0].mean_runs = Infinity;
    expect(() => validateSimulationResponse(n, exampleRequest)).toThrow();
  });
  it('rejects sample trace fields that cannot safely be displayed', () => {
    const r = copy(savedScenario.response);
    r.data.sample_match!.innings[0].deliveries![0].score = -1;
    expect(() => validateSimulationResponse(r, exampleRequest)).toThrow();
  });
});
describe('simulation HTTP boundary', () => {
  it('sends complete explicit inputs and passes through cancellation', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => savedScenario.response }),
    );
    const signal = new AbortController().signal;
    const r = await runSimulation(exampleRequest, signal);
    expect(r.data.seed).toBe(exampleRequest.seed);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/simulations/match'),
      expect.objectContaining({ method: 'POST', signal, body: JSON.stringify(exampleRequest) }),
    );
  });
  it('reports an occupied planning slot without silently substituting saved results', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 429,
        json: async () => ({ error: { code: 'planning_busy', message: 'Busy', details: null } }),
      }),
    );
    await expect(runSimulation(exampleRequest, new AbortController().signal)).rejects.toThrow(
      'Another planning run',
    );
  });
  it('keeps rule validation details for the interface', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({
          error: {
            code: 'invalid_request',
            message: 'Invalid plan',
            details: [
              { location: ['body', 'team_a', 'starting_xi'], message: 'Use eleven players' },
            ],
          },
        }),
      }),
    );
    await expect(runSimulation(exampleRequest, new AbortController().signal)).rejects.toMatchObject(
      { code: 'invalid_request', details: ['team_a / starting_xi: Use eleven players'] },
    );
  });
  it('reports connection and invalid-body failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(runSimulation(exampleRequest, new AbortController().signal)).rejects.toThrow(
      'unavailable',
    );
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => {
          throw new Error('HTML');
        },
      }),
    );
    await expect(runSimulation(exampleRequest, new AbortController().signal)).rejects.toThrow(
      'usable response',
    );
  });
});
