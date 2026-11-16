import { describe, expect, it } from 'vitest';
import { snapshots } from '../api/client';
import {
  filterMatches,
  groupMatches,
  initialFilters,
  overs,
  parseRoute,
  regularInnings,
  resultLabel,
  routeHash,
  score,
} from './archive';
import type { ArchiveSnapshot } from '../api/contracts';
import { teams } from './teams';

describe('archive selection and cricket notation', () => {
  const archive = snapshots[2026];
  const all = [...snapshots[2025].matches, ...archive.matches];
  it('keeps season records separate and sorts newest first without changing input', () => {
    const before = all.map((m) => m.match_id);
    const result = filterMatches(all, initialFilters);
    expect(result).toHaveLength(74);
    expect(result.every((m) => m.season === 2026)).toBe(true);
    expect(result[0].match_id).toBe('1535465');
    expect(all.map((m) => m.match_id)).toEqual(before);
  });
  it('combines team, ground and playoff filters', () => {
    const final = archive.matches[0];
    const result = filterMatches(all, {
      ...initialFilters,
      team: 'RCB',
      venue: final.venue_id,
      stage: 'playoffs',
    });
    expect(result.map((m) => m.match_id)).toEqual([final.match_id]);
  });
  it('separates playoff and league records', () => {
    const playoffs = filterMatches(all, { ...initialFilters, stage: 'playoffs' });
    const league = filterMatches(all, { ...initialFilters, stage: 'league' });
    expect(playoffs).toHaveLength(4);
    expect(playoffs.length + league.length).toBe(74);
    expect(league.every((m) => !m.stage)).toBe(true);
  });
  it('finds team names, references and case insensitive cities', () => {
    expect(
      filterMatches(all, { ...initialFilters, query: '  beNGALuru ' }).every(
        (m) => [m.team1_id, m.team2_id].includes('RCB') || m.city === 'Bengaluru',
      ),
    ).toBe(true);
    expect(filterMatches(all, { ...initialFilters, query: '1535465' })).toHaveLength(1);
    expect(filterMatches(all, { ...initialFilters, query: 'missing-ground-987' })).toEqual([]);
  });
  it('does not assign a winner to abandoned matches', () => {
    const noResult = filterMatches(all, { ...initialFilters, season: 2025, stage: 'no-result' });
    expect(noResult.length).toBeGreaterThan(0);
    expect(noResult.every((m) => !m.winner_id)).toBe(true);
    expect(resultLabel(noResult[0])).toBe('No result recorded');
  });
  it('groups each match once under its recorded date', () => {
    const groups = groupMatches(filterMatches(all, initialFilters));
    expect(groups.flatMap(([, rows]) => rows)).toHaveLength(74);
    expect(groups.every(([date, rows]) => rows.every((m) => m.match_date === date))).toBe(true);
  });
  it('formats legal balls in overs notation, not decimal overs', () => {
    expect(overs(119)).toBe('19.5');
    expect(overs(120)).toBe('20.0');
    expect(overs(108)).toBe('18.0');
  });
  it('keeps unknown scores distinct from a real zero score', () => {
    expect(score()).toBe('—');
    expect(score({ ...archive.innings[0], total_runs: 0, wickets: 0 })).toBe('0/0');
  });
  it('does not confuse a super over with a regular innings', () => {
    const inning = archive.innings[0];
    const regular = { ...inning, is_super_over: 0, total_runs: 180 };
    expect(regularInnings([{ ...inning, is_super_over: 1 }, regular], inning.batting_team_id)).toBe(
      regular,
    );
  });
});

describe('shareable routes', () => {
  it('opens Record without inventing a selected archive match', () => {
    expect(parseRoute(routeHash('record', initialFilters))).toEqual({
      place: 'record',
      matchId: null,
      filters: initialFilters,
    });
  });
  it('round trips combined filters and selected match', () => {
    const filters = {
      ...initialFilters,
      season: 2025 as const,
      team: 'MI',
      venue: 'venue_123',
      stage: 'playoffs' as const,
    };
    expect(parseRoute(routeHash('match', filters, '1535465'))).toEqual({
      place: 'match',
      matchId: '1535465',
      filters,
    });
  });
  it('rejects unsupported seasons, stage values and unsafe match paths', () => {
    const route = parseRoute('#/match/<script>?season=2000&stage=unknown');
    expect(route.place).toBe('fixtures');
    expect(route.filters.season).toBe(2026);
    expect(route.filters.stage).toBe('all');
  });
});

describe('saved public data and bullet contrast', () => {
  for (const season of [2025, 2026] as const) {
    it(`${season}: unique matches, correct season, connected innings and provenance`, () => {
      const archive: ArchiveSnapshot = snapshots[season];
      const ids = new Set(archive.matches.map((m) => m.match_id));
      expect(ids.size).toBe(archive.matches.length);
      expect(archive.matches.every((m) => m.season === season)).toBe(true);
      expect(archive.source_database_sha256).toMatch(/^[0-9a-f]{64}$/);
      expect(archive.innings.every((i) => ids.has(i.match_id))).toBe(true);
      expect(
        archive.innings.every((i) => i.wickets >= 0 && i.wickets <= 10 && i.legal_balls >= 0),
      ).toBe(true);
      expect(archive.matches.every((m) => !('win_probability' in m))).toBe(true);
    });
  }
  it('maintains WCAG AA text contrast in every team bullet', () => {
    function luminance(hex: string) {
      const rgb = hex
        .replace('#', '')
        .match(/.{2}/g)!
        .map((c) => parseInt(c, 16) / 255)
        .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
      return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
    }
    for (const t of Object.values(teams)) {
      const [a, b] = [luminance(t.color), luminance(t.ink)].sort((x, y) => y - x);
      expect((a + 0.05) / (b + 0.05), t.name).toBeGreaterThanOrEqual(4.5);
    }
  });
});
