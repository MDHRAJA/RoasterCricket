/** Mirrors the existing read-only API. Null means unknown, never zero. */
export interface ArchiveMatch {
  match_id: string;
  match_date: string;
  season: number;
  team1_id: string;
  team2_id: string;
  venue_id: string;
  venue_name_raw: string;
  city: string | null;
  stage: string | null;
  winner_id: string | null;
  result: string;
  win_by_runs: number | null;
  win_by_wickets: number | null;
  result_method: string | null;
  toss_winner_id: string | null;
  toss_decision: string | null;
  scheduled_overs: number;
}

export interface ArchiveInnings {
  match_id: string;
  innings: number;
  batting_team_id: string;
  bowling_team_id: string;
  total_runs: number;
  wickets: number;
  legal_balls: number;
  is_super_over: number;
}

export interface ArchiveSnapshot {
  schema: string;
  season: number;
  exported_at: string;
  source_database_sha256: string;
  provenance: string;
  matches: ArchiveMatch[];
  innings: ArchiveInnings[];
}

export interface ApiMetadata {
  dataset_version: string;
  before: string | null;
  warnings: string[];
}
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  meta: ApiMetadata;
}
export interface Envelope<T> {
  data: T;
  meta: ApiMetadata;
}
export interface MatchDetail {
  match: ArchiveMatch;
  innings: ArchiveInnings[];
  participants: Record<string, unknown>[];
  replacements: Record<string, unknown>[];
}
export type Season = 2025 | 2026;
export type DataSource = 'snapshot' | 'api';

export interface ArchiveAdapter {
  source: DataSource;
  getMatches(season: Season, signal?: AbortSignal): Promise<ArchiveMatch[]>;
  getInnings(matchId: string, signal?: AbortSignal): Promise<ArchiveInnings[]>;
}
