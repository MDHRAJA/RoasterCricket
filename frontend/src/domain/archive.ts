import type { ArchiveInnings, ArchiveMatch, Season } from '../api/contracts';
import { team } from './teams';

export function formatDate(date: string, long = false) {
  return new Intl.DateTimeFormat('en-GB', {
    day: '2-digit',
    month: long ? 'long' : 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${date}T00:00:00Z`));
}

export type StageFilter = 'all' | 'playoffs' | 'league' | 'no-result';
export interface BoardFilters {
  season: Season;
  team: string;
  venue: string;
  stage: StageFilter;
  query: string;
}
export const initialFilters: BoardFilters = {
  season: 2026,
  team: '',
  venue: '',
  stage: 'all',
  query: '',
};

export function filterMatches(matches: ArchiveMatch[], filters: BoardFilters): ArchiveMatch[] {
  const query = filters.query.trim().toLowerCase();
  return matches
    .filter((m) => {
      const playoff = Boolean(m.stage?.trim());
      return (
        Number(m.season) === filters.season &&
        (!filters.team || [m.team1_id, m.team2_id].includes(filters.team)) &&
        (!filters.venue || m.venue_id === filters.venue) &&
        (filters.stage !== 'playoffs' || playoff) &&
        (filters.stage !== 'league' || !playoff) &&
        (filters.stage !== 'no-result' || !m.winner_id) &&
        (!query ||
          [
            team(m.team1_id).name,
            team(m.team2_id).name,
            m.team1_id,
            m.team2_id,
            m.city,
            m.venue_name_raw,
            m.match_id,
            m.match_date,
            m.stage,
          ]
            .join(' ')
            .toLowerCase()
            .includes(query))
      );
    })
    .sort(
      (a, b) => b.match_date.localeCompare(a.match_date) || b.match_id.localeCompare(a.match_id),
    );
}

export function groupMatches(matches: ArchiveMatch[]): [string, ArchiveMatch[]][] {
  const grouped = new Map<string, ArchiveMatch[]>();
  for (const match of matches)
    grouped.set(match.match_date, [...(grouped.get(match.match_date) || []), match]);
  return [...grouped];
}

export function overs(balls: number): string {
  return `${Math.floor(balls / 6)}.${balls % 6}`;
}
export function score(innings?: ArchiveInnings): string {
  return innings ? `${innings.total_runs}/${innings.wickets}` : '—';
}
export function regularInnings(innings: ArchiveInnings[], teamId: string) {
  return innings.find((i) => !i.is_super_over && i.batting_team_id === teamId);
}
export function resultLabel(match: ArchiveMatch): string {
  if (!match.winner_id) return match.result === 'tie' ? 'Match tied' : 'No result recorded';
  const margin =
    match.win_by_runs != null
      ? `${match.win_by_runs} runs`
      : match.win_by_wickets != null
        ? `${match.win_by_wickets} wickets`
        : null;
  return `${team(match.winner_id).short} won${margin ? ` by ${margin}` : ''}${match.result_method ? ` · ${match.result_method}` : ''}`;
}
export function shortGround(match: ArchiveMatch): string {
  return match.venue_name_raw
    .split(',')[0]
    .replace(
      'Maharaja Yadavindra Singh International Cricket Stadium',
      'Maharaja Yadavindra Singh Stadium',
    )
    .replace('Himachal Pradesh Cricket Association Stadium', 'HPCA Stadium');
}

export type Route =
  | { place: 'fixtures'; matchId: null; filters: BoardFilters }
  | { place: 'lab'; matchId: null; filters: BoardFilters }
  | { place: 'record'; matchId: null; filters: BoardFilters }
  | { place: 'match'; matchId: string; filters: BoardFilters };

export function parseRoute(hash: string): Route {
  const [path, query = ''] = hash.replace(/^#/, '').split('?');
  const params = new URLSearchParams(query);
  const season: Season = params.get('season') === '2025' ? 2025 : 2026;
  const rawStage = params.get('stage') ?? 'all';
  const stage: StageFilter = ['all', 'playoffs', 'league', 'no-result'].includes(rawStage)
    ? (rawStage as StageFilter)
    : 'all';
  const filters = {
    season,
    stage,
    team: params.get('team') || '',
    venue: params.get('venue') || '',
    query: '',
  };
  const match = /^\/match\/([a-zA-Z0-9_-]{1,80})$/.exec(path);
  if (path === '/lab') return { place: 'lab', matchId: null, filters };
  if (path === '/record') return { place: 'record', matchId: null, filters };
  return match
    ? { place: 'match', matchId: match[1], filters }
    : { place: 'fixtures', matchId: null, filters };
}

export function routeHash(
  place: 'fixtures' | 'match' | 'lab' | 'record',
  filters: BoardFilters,
  matchId?: string,
): string {
  const params = new URLSearchParams({ season: String(filters.season) });
  if (filters.team) params.set('team', filters.team);
  if (filters.venue) params.set('venue', filters.venue);
  if (filters.stage !== 'all') params.set('stage', filters.stage);
  return `#/${place === 'lab' || place === 'record' ? place : place === 'match' && matchId ? `match/${encodeURIComponent(matchId)}` : 'fixtures'}?${params}`;
}
