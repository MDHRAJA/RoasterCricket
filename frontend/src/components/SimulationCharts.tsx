import { useId, useLayoutEffect, useRef, useState } from 'react';
import type { CompletedRun, InningsSummary, SampleInnings } from '../api/simulation';
import { outcome } from '../api/simulation';
import { histogramBins, percent, sampleAtOver, wicketOvers } from '../domain/simulation';
import { overs } from '../domain/archive';
import { team } from '../domain/teams';
import { Icon, RouteBullet, ServiceNote, SplitFlap, TagToggle } from './Signs';

export function RangeBar({ lower, upper, value }: { lower: number; upper: number; value: number }) {
  return (
    <span
      className="range-bar"
      role="img"
      aria-label={`95 percent sampling interval ${percent(lower)} to ${percent(upper)}, estimate ${percent(value)}`}
    >
      <span className="range-track" />
      <span
        className="range-span"
        style={{ left: `${lower * 100}%`, width: `${(upper - lower) * 100}%` }}
      />
      <span className="range-estimate" style={{ left: `${value * 100}%` }} />
      <span className="range-mid" />
    </span>
  );
}

export function VerdictBoard({ run }: { run: CompletedRun }) {
  const result = run.response.data,
    ids = [run.request.team_a.team_id, run.request.team_b.team_id];
  const a = outcome(result, ids[0]),
    b = outcome(result, ids[1]),
    tie = outcome(result, 'unresolved_tie');
  const overlap =
    a.sampling_interval.lower <= b.sampling_interval.upper &&
    b.sampling_interval.lower <= a.sampling_interval.upper;
  return (
    <section className="verdict-board" aria-labelledby="verdict-title">
      <div className="panel-caption">
        <h2 id="verdict-title">01 / Win estimate</h2>
        <span>Full run · {result.simulations.toLocaleString()} trials</span>
      </div>
      <div className="verdict-pair">
        {ids.map((id) => {
          const o = outcome(result, id);
          return (
            <div className="verdict-team" key={id}>
              <div className="verdict-identity">
                <RouteBullet id={id} />
                <h3>{team(id).name}</h3>
              </div>
              <SplitFlap
                value={(o.probability * 100).toFixed(1)}
                label={`${team(id).name} win probability ${percent(o.probability)}`}
              />
              <span className="verdict-unit">
                % <span>simulated win share</span>
              </span>
              <div className="interval-label">
                <span>95% sampling interval</span>
                <strong className="mono">
                  {percent(o.sampling_interval.lower)}—{percent(o.sampling_interval.upper)}
                </strong>
              </div>
              <RangeBar
                lower={o.sampling_interval.lower}
                upper={o.sampling_interval.upper}
                value={o.probability}
              />
              <div className="verdict-count mono">
                {o.count} / {result.simulations} wins
              </div>
            </div>
          );
        })}
      </div>
      <div
        className="outcome-route"
        role="img"
        aria-label={`${ids[0]} ${percent(a.probability)}, ${ids[1]} ${percent(b.probability)}, unresolved tie ${percent(tie.probability)}`}
      >
        <span style={{ width: percent(a.probability, 6), background: team(ids[0]).color }} />
        <span style={{ width: percent(b.probability, 6), background: team(ids[1]).color }} />
        <span className="tie-segment" style={{ width: percent(tie.probability, 6) }} />
      </div>
      <div className="tie-readout">
        <span>
          Unresolved tie <strong className="mono">{percent(tie.probability)}</strong>
        </span>
        <span>
          Super Over played{' '}
          <strong className="mono">{percent(result.outcomes.super_over_probability)}</strong>
        </span>
      </div>
      <p className="verdict-note">
        <span className="square-marker" />
        {overlap
          ? 'Sampling intervals overlap. This run does not clearly separate the teams.'
          : 'Sampling intervals do not overlap in this run.'}
      </p>
      <p className="verdict-caveat">
        Intervals measure simulation sampling error. They do not measure prediction accuracy or
        total model uncertainty.
      </p>
    </section>
  );
}

export function ScoreDistribution({
  innings,
  simulations,
  bins,
}: {
  innings: InningsSummary;
  simulations: number;
  bins: ReturnType<typeof histogramBins>;
}) {
  const chartId = useId(),
    [selected, setSelected] = useState<number | null>(null);
  const chartRef = useRef<SVGSVGElement>(null),
    [chartWidth, setChartWidth] = useState(680);
  useLayoutEffect(() => {
    const node = chartRef.current;
    if (!node) return;
    const update = () => setChartWidth(Math.max(250, Math.round(node.clientWidth)));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  const counts = bins.map(
    (b) => innings.score_histogram.find((h) => h.lower === b.lower)?.count || 0,
  );
  const max = Math.max(...counts),
    peak = Math.max(0.05, Math.ceil((max / simulations) * 20) / 20);
  const left = 42,
    right = 12,
    top = 19,
    bottom = 30,
    width = chartWidth,
    height = 186,
    plotW = width - left - right,
    plotH = height - top - bottom;
  const interval = bins.length ? bins.at(-1)!.upper_exclusive - bins[0].lower : 10;
  const x = (value: number) => left + ((value - bins[0].lower) / interval) * plotW;
  const active = selected === null ? null : bins[selected];
  return (
    <div className="distribution-row">
      <div className="distribution-identity">
        <RouteBullet id={innings.team_id} small />
        <strong>{team(innings.team_id).short}</strong>
        <span className="mono">Mean {innings.mean_runs.toFixed(1)} runs</span>
      </div>
      <svg
        ref={chartRef}
        className="score-chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-labelledby={`${chartId}-title ${chartId}-desc`}
      >
        <title id={`${chartId}-title`}>{team(innings.team_id).name} simulated innings totals</title>
        <desc id={`${chartId}-desc`}>
          Score histogram from {simulations} trials. Median {innings.score_quantiles.p50.toFixed(1)}{' '}
          runs. The middle 80 percent falls between {innings.score_quantiles.p10.toFixed(1)} and{' '}
          {innings.score_quantiles.p90.toFixed(1)} runs. Full bin counts are available below.
        </desc>
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line
              className="chart-rule"
              x1={left}
              x2={width - right}
              y1={top + plotH * (1 - t)}
              y2={top + plotH * (1 - t)}
            />
            <text
              className="chart-tick"
              x={left - 6}
              y={top + plotH * (1 - t) + 3}
              textAnchor="end"
            >
              {+(peak * t * 100).toFixed(1)}%
            </text>
          </g>
        ))}
        {bins.map((bin, i) => (
          <rect
            key={bin.lower}
            className={selected === i ? 'histogram-bar selected' : 'histogram-bar'}
            x={x(bin.lower) + 1}
            y={top + plotH * (1 - counts[i] / simulations / peak)}
            width={Math.max(1, plotW / bins.length - 2)}
            height={(plotH * counts[i]) / simulations / peak}
            onPointerEnter={() => setSelected(i)}
            onPointerLeave={() => setSelected(null)}
          >
            <title>
              {bin.lower}–{bin.upper_exclusive - 1} runs: {counts[i]} trials (
              {percent(counts[i] / simulations)})
            </title>
          </rect>
        ))}
        <line
          className="quantile-span"
          x1={x(innings.score_quantiles.p10)}
          x2={x(innings.score_quantiles.p90)}
          y1={top - 9}
          y2={top - 9}
        />
        <line
          className="median-tick"
          x1={x(innings.score_quantiles.p50)}
          x2={x(innings.score_quantiles.p50)}
          y1={top - 15}
          y2={top - 3}
        />
        {bins
          .filter((_, i) => i % Math.max(1, Math.ceil(bins.length / (width < 450 ? 4 : 7))) === 0)
          .map((bin) => (
            <text
              className="chart-tick"
              key={bin.lower}
              x={x(bin.lower)}
              y={height - 10}
              textAnchor="middle"
            >
              {bin.lower}
            </text>
          ))}
        <text className="chart-tick" x={width - right} y={height - 10} textAnchor="end">
          runs
        </text>
      </svg>
      <div className="distribution-summary">
        <span className="mono">
          {active
            ? `${active.lower}–${active.upper_exclusive - 1} runs · ${counts[selected!]} trials · ${percent(counts[selected!] / simulations)}`
            : `80% range ${innings.score_quantiles.p10.toFixed(1)}—${innings.score_quantiles.p90.toFixed(1)} runs`}
        </span>
        <span>
          Median <strong className="mono">{innings.score_quantiles.p50.toFixed(1)}</strong>
        </span>
      </div>
    </div>
  );
}

export function ScoreDistributions({ run }: { run: CompletedRun }) {
  const innings = run.response.data.innings,
    bins = histogramBins(innings.map((i) => i.score_histogram));
  return (
    <section className="score-distributions" aria-labelledby="distribution-title">
      <div className="panel-caption">
        <h2 id="distribution-title">02 / Innings totals</h2>
        <span>Shared run axis · 10-run bins</span>
      </div>
      {innings.map((i, index) => (
        <div key={i.team_id}>
          <div className="innings-order eyebrow">
            {index === 0 ? 'Batting first' : 'Chasing · ends when target is reached'}
          </div>
          <ScoreDistribution innings={i} simulations={run.request.simulations} bins={bins} />
        </div>
      ))}
      <div className="distribution-footnote">
        <p>
          The line above each histogram marks the middle 80% of simulated totals. The tick marks the
          median. Chase totals depend on the target and innings ending.
        </p>
        <details>
          <summary>View exact bin counts</summary>
          <div className="bin-counts">
            <table>
              <caption className="sr-only">Simulated total counts by run range</caption>
              <thead>
                <tr>
                  <th>Runs</th>
                  {innings.map((i) => (
                    <th key={i.team_id}>{i.team_id}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {bins.map((b) => (
                  <tr key={b.lower}>
                    <th scope="row">
                      {b.lower}–{b.upper_exclusive - 1}
                    </th>
                    {innings.map((i) => (
                      <td key={i.team_id}>
                        {i.score_histogram.find((v) => v.lower === b.lower)?.count || 0}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </div>
    </section>
  );
}

export function OverLine({
  innings,
  names,
}: {
  innings: SampleInnings[];
  names: Record<string, string>;
}) {
  const [side, setSide] = useState(0),
    [over, setOver] = useState(1);
  const entry = innings[side],
    maximum = Math.min(
      20,
      Math.max(
        entry.deliveries?.length ? 1 : 0,
        Math.ceil(entry.legal_balls / 6),
        Math.floor((entry.deliveries?.at(-1)?.legal_balls_before ?? -1) / 6) + 1,
      ),
    ),
    selected = Math.min(over, maximum),
    state = sampleAtOver(entry, selected);
  const wickets = wicketOvers(entry.deliveries || []),
    hasTrace = Boolean(entry.deliveries?.length);
  if (!hasTrace) return null;
  return (
    <section className="sample-timeline" aria-labelledby="over-title">
      <div className="panel-caption">
        <h2 id="over-title">03 / One simulated innings</h2>
        <span>Sample trace · not a live match</span>
      </div>
      <div className="sample-toggles">
        {innings.map((i, index) => (
          <TagToggle
            key={i.team_id}
            active={side === index}
            onClick={() => {
              setSide(index);
              setOver(1);
            }}
          >
            <RouteBullet id={i.team_id} small />
            {team(i.team_id).short}
          </TagToggle>
        ))}
        <span className="eyebrow">Sample 001</span>
      </div>
      <div className="sample-position">
        <div>
          <span className="eyebrow">After {overs(state.legal)} overs</span>
          <strong className="sample-current-score mono">
            {state.score}
            <span>/{state.wickets}</span>
          </strong>
        </div>
        <div className="sample-over-note">
          <Icon name="ball" />
          <p>
            {selected <= 6 ? 'Powerplay' : selected <= 16 ? 'Middle overs' : 'Death overs'}
            <span>{state.events.length} deliveries in this over</span>
          </p>
        </div>
      </div>
      <div className="over-stations" aria-label="Select a completed sample over">
        {Array.from({ length: 20 }, (_, i) => i + 1).map((n) => (
          <button
            key={n}
            disabled={n > maximum}
            aria-pressed={n === selected}
            aria-label={`Over ${n}${wickets.has(n) ? ', wicket recorded' : ''}${n === maximum ? `, innings ends at ${overs(entry.legal_balls)}` : ''}`}
            className={`over-station ${n <= 6 ? 'powerplay' : n <= 16 ? 'middle' : 'death'} ${wickets.has(n) ? 'has-wicket' : ''} ${n === selected ? 'selected' : ''}`}
            onClick={() => setOver(n)}
            onKeyDown={(e) => {
              if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
              e.preventDefault();
              const next = Math.max(
                1,
                Math.min(maximum, selected + (e.key === 'ArrowRight' ? 1 : -1)),
              );
              setOver(next);
              const container = e.currentTarget.parentElement;
              (container?.children[next - 1] as HTMLElement)?.focus();
            }}
          >
            <span className="station-node" />
            <span className="mono">{n}</span>
          </button>
        ))}
      </div>
      <div className="over-phases">
        <span>01–06 Powerplay</span>
        <span>07–16 Middle</span>
        <span>17–20 Death</span>
      </div>
      <div className="sample-deliveries" aria-live="polite">
        <span className="eyebrow">Over {selected}</span>
        <div className="delivery-cells">
          {state.events.map((e) => (
            <span
              key={e.physical_delivery}
              className={`delivery-cell ${e.dismissed_id ? 'wicket' : ''}`}
              title={`${names[e.striker_id] || e.striker_id} against ${names[e.bowler_id] || e.bowler_id}; ${e.batter_runs} batter runs, ${e.extras} extras; score ${e.score}/${e.wickets}`}
              aria-label={`${e.dismissed_id ? 'Wicket. ' : ''}${e.batter_runs} batter runs, ${e.extras} extras. Score ${e.score} for ${e.wickets}`}
            >
              {e.dismissed_id
                ? 'W'
                : e.kind === 'wide'
                  ? `${e.extras}wd`
                  : e.kind === 'noball'
                    ? `${e.batter_runs + e.extras}nb`
                    : e.batter_runs + e.extras === 0
                      ? '·'
                      : e.batter_runs + e.extras}
            </span>
          ))}
        </div>
      </div>
      <ServiceNote>
        Ringed stations contain a wicket. {overs(entry.legal_balls)} overs in this sample innings.
        The win estimate above remains the pre-match estimate for the full run.
      </ServiceNote>
    </section>
  );
}

export function SampleScorecard({
  run,
  names,
}: {
  run: CompletedRun;
  names: Record<string, string>;
}) {
  const [side, setSide] = useState(0),
    [mode, setMode] = useState<'batting' | 'bowling'>('batting');
  const sample = run.response.data.sample_match;
  if (!sample)
    return (
      <section className="sample-scorecard">
        <div className="panel-caption">
          <h2>Sample scorecard</h2>
        </div>
        <ServiceNote>This run did not request a sample match.</ServiceNote>
      </section>
    );
  const entry = sample.innings[side];
  return (
    <section className="sample-scorecard" aria-labelledby="sample-card-title">
      <div className="panel-caption">
        <h2 id="sample-card-title">04 / Sample scorecard</h2>
        <span>One trial · final scores</span>
      </div>
      <div className="scorecard-controls">
        <div className="filter-group">
          {sample.innings.map((i, index) => (
            <TagToggle key={i.team_id} active={index === side} onClick={() => setSide(index)}>
              {i.team_id} innings
            </TagToggle>
          ))}
        </div>
        <div className="filter-group">
          <TagToggle active={mode === 'batting'} onClick={() => setMode('batting')}>
            Batting
          </TagToggle>
          <TagToggle active={mode === 'bowling'} onClick={() => setMode('bowling')}>
            Bowling
          </TagToggle>
        </div>
      </div>
      <div className="scorecard-summary">
        <RouteBullet id={entry.team_id} />
        <h3>{team(entry.team_id).name}</h3>
        <strong className="mono">
          {entry.runs}/{entry.wickets}
          <small>{overs(entry.legal_balls)} overs</small>
        </strong>
      </div>
      <div className="sample-table-wrap">
        <table className="sample-table">
          <caption className="sr-only">
            Final {mode} scorecard for the {entry.team_id} sample innings. Player outcomes are from
            one trial, not aggregate projections.
          </caption>
          <thead>
            <tr>
              <th scope="col">{mode === 'batting' ? 'Batter' : 'Bowler'}</th>
              {(mode === 'batting'
                ? ['Status', 'Runs', 'Balls', 'SR']
                : ['Overs', 'Runs', 'Wickets', 'Econ']
              ).map((label) => (
                <th key={label} scope="col">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {mode === 'batting'
              ? entry.batting.map((p, index) => (
                  <tr key={p.player_id}>
                    <th scope="row">
                      <span className="player-order mono">
                        {String(index + 1).padStart(2, '0')}
                      </span>
                      {names[p.player_id] || p.player_id}
                    </th>
                    <td>{p.entered ? (p.dismissed ? 'Out' : 'Not out') : 'DNB'}</td>
                    <td>{p.entered ? p.runs : '—'}</td>
                    <td>{p.entered ? p.balls_faced : '—'}</td>
                    <td>
                      {p.entered && p.balls_faced
                        ? ((p.runs / p.balls_faced) * 100).toFixed(1)
                        : '—'}
                    </td>
                  </tr>
                ))
              : entry.bowling.map((p) => (
                  <tr key={p.player_id}>
                    <th scope="row">{names[p.player_id] || p.player_id}</th>
                    <td>{overs(p.legal_balls)}</td>
                    <td>{p.runs_conceded}</td>
                    <td>{p.wickets}</td>
                    <td>
                      {p.legal_balls ? ((p.runs_conceded / p.legal_balls) * 6).toFixed(2) : '—'}
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
      <div className="sample-extras mono">
        Extras {Object.values(entry.extras).reduce((a, b) => a + b, 0)}
        <span>
          Wides {entry.extras.wides ?? 0} · No-balls {entry.extras.noballs ?? 0} · Byes{' '}
          {entry.extras.byes ?? 0} · Leg-byes {entry.extras.legbyes ?? 0}
        </span>
      </div>
      <ServiceNote>
        One simulated match, not a player projection.{' '}
        {sample.winner_id
          ? `${team(sample.winner_id).short} won this sample.`
          : 'The sample finished with an unresolved tie.'}{' '}
        {sample.super_overs.length > 0
          ? `${sample.super_overs.length} Super Over rounds were played.`
          : ''}
      </ServiceNote>
    </section>
  );
}
