import type { Delivery, SampleInnings, ScoreBin, SimulationRequest } from '../api/simulation';
export const EXAMPLE_ID = 'scenario-csk-mi';
export function percent(value: number, digits = 1) {
  return `${(value * 100).toFixed(digits)}%`;
}
export function sameRequest(a: SimulationRequest, b: SimulationRequest) {
  return JSON.stringify(a) === JSON.stringify(b);
}
export function histogramBins(histograms: ScoreBin[][]) {
  const bins = histograms.flat();
  const min = Math.min(...bins.map((b) => b.lower)),
    max = Math.max(...bins.map((b) => b.upper_exclusive));
  return Array.from({ length: Math.round((max - min) / 10) }, (_, index) => ({
    lower: min + index * 10,
    upper_exclusive: min + (index + 1) * 10,
  }));
}
export function sampleAtOver(innings: SampleInnings, over: number) {
  const target = Math.max(0, Math.min(20, over)) * 6;
  const events = (innings.deliveries || []).filter((e) => e.legal_balls_before < target);
  const last = events.at(-1);
  const legal = last ? last.legal_balls_before + Number(last.kind === 'legal') : 0;
  const current = events.filter((e) => e.legal_balls_before >= Math.max(0, (over - 1) * 6));
  return {
    score: last?.score ?? 0,
    wickets: last?.wickets ?? 0,
    legal,
    events: current,
    allEvents: events,
  };
}
export function wicketOvers(deliveries: Delivery[]) {
  return new Set(
    deliveries.filter((e) => e.dismissed_id).map((e) => Math.floor(e.legal_balls_before / 6) + 1),
  );
}
export function validateArchiveContext(
  request: SimulationRequest,
  match: {
    season: number;
    team1_id: string;
    team2_id: string;
    venue_id: string;
    match_date: string;
  },
) {
  if (Number(match.season) !== 2026)
    throw new Error('The simulator supports 2026 planning scenarios only.');
  if (
    ![request.team_a.team_id, request.team_b.team_id].every((id) =>
      [match.team1_id, match.team2_id].includes(id),
    ) ||
    request.venue_id !== match.venue_id
  )
    throw new Error('Use plans for both teams at this recorded ground.');
  if (request.as_of > match.match_date)
    throw new Error(
      'For an archive replay, the evidence cutoff must be on or before the recorded match date.',
    );
}
