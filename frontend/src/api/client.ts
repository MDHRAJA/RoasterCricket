import type {
  ArchiveAdapter,
  ArchiveInnings,
  ArchiveMatch,
  Envelope,
  MatchDetail,
  Page,
  Season,
} from './contracts';
import archive2025 from './snapshots/2025.json';
import archive2026 from './snapshots/2026.json';

export const snapshots = { 2025: archive2025, 2026: archive2026 };

function validateMatch(value: unknown): value is ArchiveMatch {
  if (!value || typeof value !== 'object') return false;
  const row = value as Record<string, unknown>;
  return (
    [
      'match_id',
      'match_date',
      'team1_id',
      'team2_id',
      'venue_id',
      'venue_name_raw',
      'result',
    ].every((key) => typeof row[key] === 'string') &&
    /^\d{4}-\d{2}-\d{2}$/.test(String(row.match_date)) &&
    Number.isInteger(Number(row.season))
  );
}

function validateInnings(value: unknown, matchId: string): value is ArchiveInnings {
  if (!value || typeof value !== 'object') return false;
  const row = value as Record<string, unknown>;
  return (
    row.match_id === matchId &&
    typeof row.batting_team_id === 'string' &&
    typeof row.bowling_team_id === 'string' &&
    ['innings', 'total_runs', 'wickets', 'legal_balls'].every(
      (key) => typeof row[key] === 'number' && Number.isInteger(row[key]) && Number(row[key]) >= 0,
    ) &&
    [0, 1, false, true].includes(row.is_super_over as number)
  );
}

const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    headers: { Accept: 'application/json' },
    signal,
  });
  if (!response.ok) throw new Error(`Archive request returned ${response.status}`);
  return response.json() as Promise<T>;
}

export const liveAdapter: ArchiveAdapter = {
  source: 'api',
  async getMatches(season, signal) {
    const data = await get<Page<ArchiveMatch>>(
      `/matches?season=${season}&limit=100&offset=0`,
      signal,
    );
    if (
      !Array.isArray(data.items) ||
      !data.items.every(validateMatch) ||
      data.items.some((m) => Number(m.season) !== season)
    ) {
      throw new Error('Archive response does not match the supported contract');
    }
    if (!Number.isInteger(data.total) || data.total !== data.items.length || data.offset !== 0)
      throw new Error('Archive page is incomplete');
    return data.items.map((m) => ({ ...m, season: Number(m.season) }));
  },
  async getInnings(matchId, signal) {
    const data = await get<Envelope<MatchDetail>>(
      `/matches/${encodeURIComponent(matchId)}`,
      signal,
    );
    if (
      !data.data ||
      !Array.isArray(data.data.innings) ||
      data.data.match?.match_id !== matchId ||
      !data.data.innings.every((i) => validateInnings(i, matchId))
    )
      throw new Error('Match detail response is incomplete');
    return data.data.innings;
  },
};

export const snapshotAdapter: ArchiveAdapter = {
  source: 'snapshot',
  async getMatches(season: Season) {
    return snapshots[season].matches;
  },
  async getInnings(matchId) {
    return [...archive2025.innings, ...archive2026.innings].filter((i) => i.match_id === matchId);
  },
};

export function savedInnings(matchId: string): ArchiveInnings[] {
  return [...archive2025.innings, ...archive2026.innings].filter((i) => i.match_id === matchId);
}
