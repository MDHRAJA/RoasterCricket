import { describe, expect, it } from 'vitest';
import { exampleRequest, savedRun, type Delivery, type SampleInnings } from '../api/simulation';
import {
  histogramBins,
  sampleAtOver,
  sameRequest,
  validateArchiveContext,
  wicketOvers,
} from './simulation';

const innings = savedRun.response.data.sample_match!.innings[0];
describe('sample-innings timeline', () => {
  it('starts at zero and reconciles the final sample score', () => {
    expect(sampleAtOver(innings, 0)).toMatchObject({ score: 0, wickets: 0, legal: 0, events: [] });
    expect(sampleAtOver(innings, 20)).toMatchObject({
      score: innings.runs,
      wickets: innings.wickets,
      legal: innings.legal_balls,
    });
  });
  it('keeps illegal deliveries in their actual over without moving the station early', () => {
    const base = innings.deliveries![0];
    const events: Delivery[] = [
      { ...base, kind: 'wide', legal_balls_before: 5, score: 10 },
      { ...base, kind: 'legal', legal_balls_before: 5, score: 11 },
      { ...base, kind: 'wide', legal_balls_before: 6, score: 12 },
    ];
    const entry = { ...innings, deliveries: events };
    expect(sampleAtOver(entry, 1)).toMatchObject({ score: 11, legal: 6 });
    expect(sampleAtOver(entry, 1).events).toHaveLength(2);
    expect(sampleAtOver(entry, 2).events).toHaveLength(1);
  });
  it('does not fabricate remaining overs when a chase ends early', () => {
    const entry: SampleInnings = {
      ...innings,
      legal_balls: 7,
      deliveries: [{ ...innings.deliveries![0], kind: 'legal', legal_balls_before: 6, score: 42 }],
    };
    expect(sampleAtOver(entry, 2)).toMatchObject({ score: 42, legal: 7 });
    const wideFinish: SampleInnings = {
      ...innings,
      legal_balls: 0,
      deliveries: [{ ...innings.deliveries![0], kind: 'wide', legal_balls_before: 0, score: 1 }],
    };
    expect(sampleAtOver(wideFinish, 1)).toMatchObject({ score: 1, legal: 0 });
  });
  it('locates wickets by legal-ball position', () => {
    const e = innings.deliveries![0];
    expect([
      ...wicketOvers([
        { ...e, legal_balls_before: 5, dismissed_id: 'p1' },
        { ...e, legal_balls_before: 6, dismissed_id: 'p2' },
      ]),
    ]).toEqual([1, 2]);
  });
});
describe('comparison scope and score bins', () => {
  it('fills absent 10-run bins with shared axis positions, without creating trials', () => {
    expect(
      histogramBins([
        [{ lower: 100, upper_exclusive: 110, count: 2 }],
        [{ lower: 120, upper_exclusive: 130, count: 1 }],
      ]),
    ).toEqual([
      { lower: 100, upper_exclusive: 110 },
      { lower: 110, upper_exclusive: 120 },
      { lower: 120, upper_exclusive: 130 },
    ]);
  });
  it('marks pending inputs when seed, assumptions or trial count differ', () => {
    expect(sameRequest(exampleRequest, structuredClone(exampleRequest))).toBe(true);
    expect(sameRequest(exampleRequest, { ...exampleRequest, seed: 1 })).toBe(false);
    expect(
      sameRequest(exampleRequest, { ...exampleRequest, allow_unknown_availability: false }),
    ).toBe(false);
  });
  it('prevents unrelated or future-evidence plans being attached to an archive result', () => {
    const match = {
      season: 2026,
      team1_id: 'CSK',
      team2_id: 'MI',
      venue_id: exampleRequest.venue_id,
      match_date: exampleRequest.as_of,
    };
    expect(() => validateArchiveContext(exampleRequest, match)).not.toThrow();
    expect(() => validateArchiveContext(exampleRequest, { ...match, team2_id: 'RCB' })).toThrow(
      'both teams',
    );
    expect(() =>
      validateArchiveContext(exampleRequest, { ...match, match_date: '2026-04-01' }),
    ).toThrow('cutoff');
    expect(() => validateArchiveContext(exampleRequest, { ...match, season: 2025 })).toThrow(
      '2026',
    );
  });
});
