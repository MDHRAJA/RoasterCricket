import { describe, expect, it } from 'vitest';
import { recordData, validateRecord } from './record';
import {
  actualWinner,
  correctPick,
  filterForecasts,
  pickedTeam,
  pickProbability,
  pairedGainNote,
} from '../domain/record';

describe('saved research evidence', () => {
  it('retains all 353 selected-recipe forecasts with independently reconcilable season counts', () => {
    expect(validateRecord(recordData)).toBe(true);
    expect(recordData.winner.forecasts).toHaveLength(353);
    expect(
      recordData.winner.seasons.map((s) => [s.season, s.metrics.n, s.metrics.correct]),
    ).toEqual([
      [2022, 74, 38],
      [2023, 71, 39],
      [2024, 70, 39],
      [2025, 68, 36],
      [2026, 70, 39],
    ]);
    expect(recordData.winner.seasons.slice(0, 4).every((s) => s.phase === 'selection')).toBe(true);
    expect(recordData.winner.seasons[4].phase).toBe('final');
  });
  it('links to the exact saved source reports, model, protocol and integrity artifacts', async () => {
    const sources = import.meta.glob(
      [
        '../../../outputs/match-winner-research.json',
        '../../../outputs/match-winner-checks.json',
        '../../../outputs/match-winner-model.json',
        '../../../outputs/winner-research-protocol.json',
        '../../../outputs/winner-selection-lock.json',
        '../../../outputs/full-match-backtest.json',
        '../../../outputs/match-backtest-checks.json',
        '../../../outputs/match-score-calibration-audit.json',
        '../../../outputs/delivery-calibration-backtest.json',
      ],
      { query: '?raw', import: 'default' },
    );
    for (const source of recordData.sources) {
      const text = (await sources[`../../../${source.path}`]()) as string;
      const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
      const hex = Array.from(new Uint8Array(hash), (b) => b.toString(16).padStart(2, '0')).join('');
      expect(hex, source.path).toBe(source.sha256);
    }
  });
  it('preserves the failed target and stronger same-cohort chasing baseline', () => {
    const final = recordData.winner.seasons[4].metrics;
    expect(recordData.winner.target).toBe(0.7);
    expect(recordData.winner.targetMet).toBe(false);
    expect(final.correct).toBe(39);
    expect(recordData.winner.baselines.neutral_50_percent_ties_choose_chase.correct).toBe(45);
    expect(recordData.winner.baselines.prior_order_history.n).toBe(final.n);
    expect(recordData.winner.accuracyInterval.upper).toBeLessThan(0.7);
  });
  it('does not pool simulator populations or conflate 400 draws with forecast count', () => {
    const sim = recordData.simulator;
    expect(sim.trials).toBe(400);
    expect(sim.eligible).toBe(208);
    expect(sim.cohorts).toEqual({
      population: 208,
      participant_raw: 204,
      participant_delivery_corrected: 135,
    });
    const final = sim.seasons.find((s) => s.season === 2026)!;
    expect(final.variants.population.metrics.n).toBe(70);
    expect(final.variants.participant_raw.metrics.n).toBe(67);
    expect(final.variants.participant_delivery_corrected.metrics.n).toBe(67);
    expect(sim.formatExclusions).toHaveLength(11);
    expect(sim.poolExclusions).toHaveLength(4);
  });
  it('pairs coverage gains with larger widths and retained uncertainty', () => {
    const comparison = recordData.simulator.seasons[1].scores.participant_raw;
    expect(comparison.raw.covered).toBe(44);
    expect(comparison.candidate.covered).toBe(64);
    expect(comparison.raw.n).toBe(comparison.candidate.n);
    expect(comparison.candidate.width).toBeGreaterThan(comparison.raw.width);
    expect(comparison.maeGain.lower).toBeLessThan(0);
    expect(comparison.intervalGain.lower).toBeLessThan(0);
  });
  it('keeps delivery units and match-cluster uncertainty separate', () => {
    expect(recordData.delivery.fitDeliveries).toBe(16299);
    for (const s of recordData.delivery.seasons) {
      expect(s.raw.n).toBeGreaterThan(s.raw.matches * 100);
      expect(s.gain.lower).toBeLessThan(0);
      expect(s.gain.upper).toBeGreaterThan(0);
      expect(s.corrected.events.boundary.ece).toBeLessThan(s.raw.events.boundary.ece);
    }
  });
  it('withholds inconsistent counts, intervals, probabilities and a false target-success claim', () => {
    for (const mutate of [
      (d: typeof recordData) => {
        d.winner.targetMet = true;
      },
      (d: typeof recordData) => {
        d.winner.seasons[4].metrics.correct = 40;
      },
      (d: typeof recordData) => {
        d.winner.seasons[4].metrics.bins[0].n++;
      },
      (d: typeof recordData) => {
        d.winner.forecasts[0].probability = NaN;
      },
      (d: typeof recordData) => {
        d.winner.forecasts[0].id = d.winner.forecasts[1].id;
      },
      (d: typeof recordData) => {
        d.winner.forecasts[0].latestEvidence = d.winner.forecasts[0].date;
      },
      (d: typeof recordData) => {
        d.simulator.seasons[0].scores.population.raw.covered++;
      },
      (d: typeof recordData) => {
        d.winner.accuracyInterval.lower = 0.9;
      },
      (d: typeof recordData) => {
        d.sources[0].sha256 = 'wrong';
      },
    ]) {
      const copy = structuredClone(recordData);
      mutate(copy);
      expect(validateRecord(copy)).toBe(false);
    }
  });
});

describe('research forecast inspection', () => {
  it('distinguishes an interval spanning zero from evidence favoring the baseline', () => {
    const sim = recordData.simulator.seasons[0];
    expect(pairedGainNote(Object.values(sim.variants.participant_raw.gain))).toContain(
      'include zero',
    );
    expect(
      pairedGainNote(Object.values(sim.variants.participant_delivery_corrected.gain)),
    ).toContain('favor the neutral baseline');
  });
  it('uses chasing at exactly 50 percent without changing the probability orientation', () => {
    const p = { ...recordData.winner.forecasts[0], probability: 0.5, outcome: 0 };
    expect(pickedTeam(p)).toBe(p.chase);
    expect(actualWinner(p)).toBe(p.chase);
    expect(correctPick(p)).toBe(true);
    expect(pickProbability(p)).toBe(0.5);
    expect(pickedTeam({ ...p, probability: 0.51 })).toBe(p.first);
    expect(pickProbability({ ...p, probability: 0.3 })).toBe(0.7);
  });
  it('partitions all final forecasts into 39 right and 31 wrong without filtering aggregate evidence', () => {
    const rows = recordData.winner.forecasts;
    expect(filterForecasts(rows, 2026, 'right', '')).toHaveLength(39);
    expect(filterForecasts(rows, 2026, 'wrong', '')).toHaveLength(31);
    expect(filterForecasts(rows, 2026, 'all', '')).toHaveLength(70);
    expect(filterForecasts(rows, 2025, 'all', '')).toHaveLength(68);
  });
  it('combines search and result filters with empty states', () => {
    const row = recordData.winner.forecasts.find((p) => p.season === 2026)!;
    expect(filterForecasts(recordData.winner.forecasts, 2026, 'all', row.id)).toEqual([row]);
    expect(filterForecasts(recordData.winner.forecasts, 2025, 'all', row.id)).toEqual([]);
    expect(filterForecasts(recordData.winner.forecasts, 2026, 'all', 'unknown ground')).toEqual([]);
  });
  it('exposes actual prior-date traces only where retained', () => {
    expect(
      recordData.winner.forecasts
        .filter((p) => p.season === 2026)
        .every((p) => p.latestEvidence !== null && p.latestEvidence < p.date),
    ).toBe(true);
    expect(
      recordData.winner.forecasts
        .filter((p) => p.season < 2026)
        .every((p) => p.latestEvidence === null),
    ).toBe(true);
  });
});
