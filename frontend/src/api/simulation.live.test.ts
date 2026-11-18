import { describe, expect, it } from 'vitest';
import { exampleRequest, runSimulation, type SimulationRequest } from './simulation';

// Explicitly opt in: these checks send sequential, small runs to a real service.
describe.skipIf(import.meta.env.VITE_LIVE_MATCH_QA !== '1')('live Match service', () => {
  it('returns reproducible seed-zero results with a complete sample trace', async () => {
    const request = { ...exampleRequest, simulations: 50, seed: 0 };
    const one = await runSimulation(request, AbortSignal.timeout(45000));
    const two = await runSimulation(request, AbortSignal.timeout(45000));
    expect(one.data).toEqual(two.data);
    expect(one.data.sample_match!.innings[0].team_id).toBe('CSK');
    expect(one.data.eligibility_verified).toBe(false);
  }, 100000);

  it('supports reversed batting order and a run without a sample', async () => {
    const request: SimulationRequest = {
      ...exampleRequest,
      simulations: 50,
      seed: 0,
      batting_first_team_id: 'MI',
      include_sample_match: false,
    };
    const result = await runSimulation(request, AbortSignal.timeout(45000));
    expect(result.data.innings.map((i) => i.team_id)).toEqual(['MI', 'CSK']);
    expect(result.data.sample_match).toBeNull();
  }, 55000);

  it('returns the complete 200-trial example through frontend validation', async () => {
    const result = await runSimulation(exampleRequest, AbortSignal.timeout(45000));
    expect(result.data.simulations).toBe(200);
    expect(result.data.sample_match!.innings).toHaveLength(2);
    expect(result.meta.before).toBe(exampleRequest.as_of);
  }, 55000);

  it('rejects unknown availability without inventing a completed run', async () => {
    await expect(
      runSimulation(
        { ...exampleRequest, simulations: 50, allow_unknown_availability: false },
        AbortSignal.timeout(45000),
      ),
    ).rejects.toMatchObject({
      code: expect.any(String),
      message: expect.stringMatching(/availability/i),
    });
  }, 55000);
});
