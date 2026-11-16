import type { Gain, ResearchForecast } from '../api/record';
export type ResultFilter = 'all' | 'right' | 'wrong';
export function pairedGainNote(gains: Gain[]) {
  if (gains.every((g) => g.upper < 0))
    return 'Both paired intervals favor the neutral baseline over this variant.';
  if (gains.every((g) => g.lower <= 0 && g.upper >= 0))
    return 'Both paired intervals include zero; a winner-prediction advantage is not established.';
  return 'The paired intervals differ; inspect each metric separately. They do not establish a future accuracy guarantee.';
}
export function pickedTeam(p: ResearchForecast) {
  return p.probability > 0.5 ? p.first : p.chase;
}
export function actualWinner(p: ResearchForecast) {
  return p.outcome === 1 ? p.first : p.chase;
}
export function correctPick(p: ResearchForecast) {
  return pickedTeam(p) === actualWinner(p);
}
export function pickProbability(p: ResearchForecast) {
  return p.probability > 0.5 ? p.probability : 1 - p.probability;
}
export function filterForecasts(
  rows: ResearchForecast[],
  season: number,
  result: ResultFilter,
  query: string,
) {
  const needle = query.trim().toLowerCase();
  return rows.filter(
    (p) =>
      p.season === season &&
      (result === 'all' || correctPick(p) === (result === 'right')) &&
      (!needle ||
        [p.id, p.date, p.first, p.chase, p.ground].join(' ').toLowerCase().includes(needle)),
  );
}
export function signedMetric(n: number, digits = 5) {
  return `${n > 0 ? '+' : ''}${n.toFixed(digits)}`;
}
