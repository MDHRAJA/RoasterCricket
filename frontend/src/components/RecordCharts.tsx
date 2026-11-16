import { useId, useLayoutEffect, useRef, useState } from 'react';
import type { CalibrationBin, RecordMetrics } from '../api/record';
import { percent } from '../domain/simulation';

export function CalibrationChart({ metrics, label }: { metrics: RecordMetrics; label: string }) {
  const ref = useRef<HTMLDivElement>(null),
    [width, setWidth] = useState(540),
    [selected, setSelected] = useState(0),
    title = useId();
  useLayoutEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(250, Math.floor(entry.contentRect.width))),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const active = Math.min(selected, metrics.bins.length - 1),
    bin = metrics.bins[active];
  const height = width < 400 ? 300 : 340,
    left = 48,
    right = 20,
    top = 24,
    bottom = height - 48;
  const x = (p: number) => left + p * (width - left - right),
    y = (p: number) => bottom - p * (bottom - top);
  const selectBin = (b: CalibrationBin, i: number) => (
    <g
      key={b.lower}
      className={`calibration-point ${active === i ? 'selected' : ''}`}
      role="button"
      tabIndex={0}
      aria-pressed={active === i}
      aria-label={`Bin ${i + 1}: ${b.n} matches, predicted ${percent(b.mean)}, observed ${percent(b.observed)}. Select details.`}
      onClick={() => setSelected(i)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          setSelected(i);
        }
      }}
    >
      <title>
        {b.n} matches · {b.wins} batting-first wins · 95% approximate interval{' '}
        {percent(b.interval.lower)}–{percent(b.interval.upper)}
      </title>
      <path
        className="calibration-whisker"
        d={`M${x(b.mean)},${y(b.interval.lower)}V${y(b.interval.upper)}M${x(b.mean) - 5},${y(b.interval.lower)}h10M${x(b.mean) - 5},${y(b.interval.upper)}h10`}
      />
      <circle className="point-hit" cx={x(b.mean)} cy={y(b.observed)} r={14} />
      <circle className="point-dot" cx={x(b.mean)} cy={y(b.observed)} r={active === i ? 7 : 5} />
    </g>
  );
  return (
    <div className="record-calibration" ref={ref}>
      <figure>
        <svg viewBox={`0 0 ${width} ${height}`} aria-labelledby={title} role="group">
          <title id={title}>
            {label}. Predicted probability and observed batting-first win frequency. Approximate 95
            percent binomial intervals.
          </title>
          {[0, 0.25, 0.5, 0.75, 1].map((t) => (
            <g key={t} className="calibration-grid">
              <path d={`M${left},${y(t)}H${width - right}M${x(t)},${top}V${bottom}`} />
              <text x={left - 10} y={y(t) + 4} textAnchor="end">
                {t * 100}%
              </text>
              <text x={x(t)} y={bottom + 20} textAnchor="middle">
                {t * 100}%
              </text>
            </g>
          ))}
          <path className="calibration-diagonal" d={`M${x(0)},${y(0)}L${x(1)},${y(1)}`} />
          <text className="calibration-axis" x={left} y={13}>
            Observed wins · batting first
          </text>
          <text className="calibration-axis" x={width - right} y={height - 4} textAnchor="end">
            Predicted probability →
          </text>
          {metrics.bins.map(selectBin)}
        </svg>
        <figcaption>
          Diagonal = equal predicted and observed rates. Whiskers = 95% Wilson bin intervals, an
          independence approximation. They are not a fitted confidence band or future guarantee.
        </figcaption>
      </figure>
      <div className="bin-selector" aria-label="Calibration bin details">
        {metrics.bins.map((b, i) => (
          <button key={b.lower} aria-pressed={active === i} onClick={() => setSelected(i)}>
            <span className="mono">
              {Math.round(b.lower * 100)}–{Math.round(b.upper * 100)}%
            </span>
            <strong>{b.n}</strong>
            <span>matches</span>
          </button>
        ))}
      </div>
      {bin && (
        <div className="bin-detail" aria-live="polite">
          <span>
            <b className="mono">
              {bin.wins}/{bin.n}
            </b>{' '}
            observed wins
          </span>
          <span>
            Mean forecast <b className="mono">{percent(bin.mean)}</b>
          </span>
          <span>
            Observed <b className="mono">{percent(bin.observed)}</b>
          </span>
        </div>
      )}
      <details className="record-exact">
        <summary>Exact calibration counts and intervals</summary>
        <div
          className="record-table-scroll"
          tabIndex={0}
          role="region"
          aria-label="Exact calibration data"
        >
          <table>
            <caption>{label}; empty 10% bins omitted</caption>
            <thead>
              <tr>
                <th scope="col">Bin</th>
                <th scope="col">Matches</th>
                <th scope="col">Mean</th>
                <th scope="col">Wins</th>
                <th scope="col">Observed</th>
                <th scope="col">95% interval</th>
              </tr>
            </thead>
            <tbody>
              {metrics.bins.map((b) => (
                <tr key={b.lower}>
                  <th scope="row">
                    {percent(b.lower, 0)}–{percent(b.upper, 0)}
                  </th>
                  <td>{b.n}</td>
                  <td>{percent(b.mean, 2)}</td>
                  <td>{b.wins}</td>
                  <td>{percent(b.observed, 2)}</td>
                  <td>
                    {percent(b.interval.lower, 2)}–{percent(b.interval.upper, 2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
