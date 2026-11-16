import { useEffect, useRef, useState } from 'react';
import {
  downloadEvidence,
  recordData,
  validateRecord,
  type Gain,
  type RecordMetrics,
  type ResearchForecast,
  type SimulatorVariant,
} from '../api/record';
import {
  actualWinner,
  correctPick,
  filterForecasts,
  pickedTeam,
  pickProbability,
  pairedGainNote,
  signedMetric,
  type ResultFilter,
} from '../domain/record';
import { formatDate } from '../domain/archive';
import { percent } from '../domain/simulation';
import { CalibrationChart } from './RecordCharts';
import { Icon, RouteBullet, ServiceNote, SplitFlap, TagToggle } from './Signs';
import '../record.css';

const data = recordData,
  valid = validateRecord(data);
type EvidenceView = 'winner' | 'simulator' | 'delivery';
function Heading({ number, title, note }: { number: string; title: string; note?: string }) {
  return (
    <div className="record-panel-heading">
      <div>
        <span className="eyebrow">{number}</span>
        <h2>{title}</h2>
      </div>
      {note && <span className="mono">{note}</span>}
    </div>
  );
}
function MetricsRow({
  name,
  metrics,
  note,
}: {
  name: string;
  metrics: RecordMetrics;
  note?: string;
}) {
  return (
    <tr>
      <th scope="row">
        {name}
        {note && <small>{note}</small>}
      </th>
      <td>{metrics.n}</td>
      <td>{percent(metrics.accuracy)}</td>
      <td>{metrics.brier.toFixed(5)}</td>
      <td>{metrics.logLoss.toFixed(5)}</td>
    </tr>
  );
}
function MetricsHead() {
  return (
    <thead>
      <tr>
        <th scope="col">Predictor</th>
        <th scope="col">Matches</th>
        <th scope="col">Pick accuracy</th>
        <th scope="col">Brier ↓</th>
        <th scope="col">Log loss ↓</th>
      </tr>
    </thead>
  );
}
function GainReadout({ label, value }: { label: string; value: Gain }) {
  return (
    <div className="record-gain">
      <span>{label}</span>
      <strong className="mono">{signedMetric(value.mean)}</strong>
      <span className="mono">
        95%: {signedMetric(value.lower)} to {signedMetric(value.upper)}
      </span>
    </div>
  );
}

function ForecastLedger({ season }: { season: number }) {
  const receiptRef = useRef<HTMLDivElement>(null),
    originRef = useRef<HTMLButtonElement | null>(null);
  const [result, setResult] = useState<ResultFilter>('all'),
    [query, setQuery] = useState(''),
    [limit, setLimit] = useState(14),
    [selected, setSelected] = useState<string | null>(null);
  const rows = filterForecasts(data.winner.forecasts, season, result, query),
    all = data.winner.forecasts.filter((p) => p.season === season);
  const detail = rows.find((p) => p.id === selected);
  useEffect(() => {
    if (selected) receiptRef.current?.focus();
  }, [selected]);
  function choose(p: ResearchForecast) {
    setSelected(selected === p.id ? null : p.id);
  }
  return (
    <section className="record-ledger">
      <Heading
        number="04 / Forecast ledger"
        title="Every pick. Every outcome."
        note={`${season} / ${all.length} forecasts`}
      />
      <div
        className="forecast-strip"
        aria-label={`${season} chronological results. R means right, W means wrong.`}
      >
        {all.map((p, i) => (
          <button
            key={p.id}
            className={`${correctPick(p) ? 'right' : 'wrong'} ${selected === p.id ? 'selected' : ''}`}
            aria-label={`Match ${i + 1}, ${p.first} versus ${p.chase}, ${formatDate(p.date)}, ${correctPick(p) ? 'right' : 'wrong'}. Show forecast.`}
            onClick={(e) => {
              originRef.current = e.currentTarget;
              setResult('all');
              setQuery('');
              setLimit(all.length);
              setSelected(p.id);
            }}
          >
            <span>{correctPick(p) ? 'R' : 'W'}</span>
          </button>
        ))}
      </div>
      <div className="record-ledger-tools">
        <div className="filter-group" aria-label="Forecast outcome">
          {(['all', 'right', 'wrong'] as const).map((r) => (
            <TagToggle
              active={result === r}
              key={r}
              onClick={() => {
                setResult(r);
                setLimit(14);
                setSelected(null);
              }}
            >
              {r === 'all' ? 'All picks' : r === 'right' ? 'Right' : 'Wrong'}{' '}
              <span className="mono">
                {r === 'all'
                  ? all.length
                  : all.filter((p) => correctPick(p) === (r === 'right')).length}
              </span>
            </TagToggle>
          ))}
        </div>
        <label className="record-search">
          <Icon name="search" />
          <input
            aria-label="Search research forecasts"
            placeholder="Team, date, ground, reference…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setLimit(14);
              setSelected(null);
            }}
          />
          {query && (
            <button aria-label="Clear forecast search" onClick={() => setQuery('')}>
              <Icon name="close" />
            </button>
          )}
        </label>
      </div>
      <div className="ledger-count mono" role="status">
        {rows.length} of {all.length} forecasts shown by these filters. Summary metrics above use
        all {all.length}.
      </div>
      {detail && (
        <div
          className="forecast-receipt"
          ref={receiptRef}
          tabIndex={-1}
          role="region"
          aria-label={`Forecast ${detail.id}`}
        >
          <div>
            <span className="eyebrow">Forecast receipt / {detail.id}</span>
            <h3>
              {detail.first} v {detail.chase}
            </h3>
            <p>
              {formatDate(detail.date)} · {detail.ground}
            </p>
          </div>
          <dl>
            <div>
              <dt>Batting-first probability</dt>
              <dd>
                {percent(detail.probability, 3)} / {detail.first}
              </dd>
            </div>
            <div>
              <dt>Picked</dt>
              <dd>
                {pickedTeam(detail)} · {percent(pickProbability(detail), 3)}
              </dd>
            </div>
            <div>
              <dt>Recorded winner</dt>
              <dd>
                {actualWinner(detail)} · {correctPick(detail) ? 'Right' : 'Wrong'}
              </dd>
            </div>
            <div>
              <dt>Latest feature evidence</dt>
              <dd>
                {detail.latestEvidence
                  ? formatDate(detail.latestEvidence)
                  : 'Per-match trace absent in selection extract'}
              </dd>
            </div>
          </dl>
          <ServiceNote>
            {season === 2026
              ? 'Frozen weights trained on 2012–2025. Earlier 2026 results update later features; same-day evidence is excluded.'
              : 'An earlier-season validation fold used in recipe selection. This is not an untouched final evaluation.'}
          </ServiceNote>
          <button
            className="text-button"
            onClick={() => {
              setSelected(null);
              originRef.current?.focus();
            }}
          >
            Close receipt ×
          </button>
        </div>
      )}
      {rows.length ? (
        <div className="forecast-rows">
          <div className="forecast-columns" aria-hidden="true">
            <span>Date / reference</span>
            <span>Match / ground</span>
            <span>Picked / probability</span>
            <span>Winner</span>
            <span>Result</span>
          </div>
          {rows.slice(0, limit).map((p) => (
            <button
              className={`forecast-row ${selected === p.id ? 'selected' : ''}`}
              key={p.id}
              aria-expanded={selected === p.id}
              aria-label={`${formatDate(p.date)}, ${p.first} versus ${p.chase}. Picked ${pickedTeam(p)} at ${percent(pickProbability(p))}. Winner ${actualWinner(p)}. ${correctPick(p) ? 'Right' : 'Wrong'}. Show receipt.`}
              onClick={(e) => {
                originRef.current = e.currentTarget;
                choose(p);
              }}
            >
              <span className="forecast-date mono">
                {formatDate(p.date)}
                <small>#{p.id}</small>
              </span>
              <span className="forecast-match">
                <span>
                  <RouteBullet id={p.first} small />
                  <b>{p.first}</b>
                  <span className="versus">v</span>
                  <RouteBullet id={p.chase} small />
                  <b>{p.chase}</b>
                </span>
                <small>{p.ground}</small>
              </span>
              <span className="forecast-picked">
                <b>{pickedTeam(p)}</b>
                <span className="mono">{percent(pickProbability(p))}</span>
              </span>
              <span className="forecast-winner">
                <span className="mobile-label">Won </span>
                {actualWinner(p)}
              </span>
              <span className={`pick-result ${correctPick(p) ? 'right' : 'wrong'}`}>
                {correctPick(p) ? 'RIGHT' : 'WRONG'}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <div className="record-empty">
          <h3>No forecasts match.</h3>
          <button
            className="text-button"
            onClick={() => {
              setResult('all');
              setQuery('');
            }}
          >
            Clear forecast filters →
          </button>
        </div>
      )}
      {rows.length > limit && (
        <button className="record-more" onClick={() => setLimit((n) => n + 20)}>
          Show next {Math.min(20, rows.length - limit)} forecasts <Icon name="arrow" />
        </button>
      )}
      <p className="record-footnote">
        Chronological order. Probability in each row belongs to the picked team. Calibration uses
        batting-first probability. At exactly 50%, the pick is the chasing side.
      </p>
    </section>
  );
}

function WinnerEvidence() {
  const [season, setSeason] = useState(2026),
    w = data.winner,
    final = w.seasons.find((s) => s.season === 2026)!,
    current = w.seasons.find((s) => s.season === season)!;
  return (
    <>
      <div className="research-verdict">
        <div className="research-headline">
          <span className="eyebrow">Direct winner research / final 2026 evaluation</span>
          <SplitFlap
            value={(final.metrics.accuracy * 100).toFixed(1)}
            label={`${percent(final.metrics.accuracy)} accuracy on all ${final.metrics.n} eligible 2026 matches`}
          />
          <span className="record-unit">
            % correct picks{' '}
            <b className="mono">
              {final.metrics.correct} / {final.metrics.n}
            </b>
          </span>
          <p>70% target missed.</p>
          <span className="mono">
            95% approximate accuracy interval: {percent(w.accuracyInterval.lower)}–
            {percent(w.accuracyInterval.upper)}
          </span>
        </div>
        <div className="research-baseline">
          <span className="eyebrow">Same 70 matches / always choose chasing side</span>
          <strong className="record-baseline-number">
            {percent(w.baselines.neutral_50_percent_ties_choose_chase.accuracy)}
          </strong>
          <span className="mono">
            {w.baselines.neutral_50_percent_ties_choose_chase.correct} / {final.metrics.n} correct
          </span>
          <h2>No demonstrated advantage.</h2>
          <p>
            The selected model trails this simple decision rule. Probability-score comparison
            intervals also cross zero.
          </p>
          <span className="record-status">Research only · not used in Lab</span>
        </div>
      </div>
      <div className="record-protocol">
        <div>
          <span className="eyebrow">01 / Chronological protocol</span>
          <h2>Earlier dates only.</h2>
        </div>
        <ol>
          <li>
            <b>{w.trainingStart}–2021</b>
            <span>Earlier training history</span>
          </li>
          <li>
            <b>2022–2025</b>
            <span>Recipe selection / {w.selectionRecipes} choices</span>
          </li>
          <li>
            <b>2026</b>
            <span>Frozen-weight final evaluation</span>
          </li>
        </ol>
        <p>
          2026 had already been inspected in other diagnostics. This is a retrospective evaluation,
          not a new prospective trial. The selected shallow forest excludes reconstructed-XI
          features.
        </p>
      </div>
      <div className="record-main-grid">
        <section className="record-seasons">
          <Heading
            number="02 / Season record"
            title="Selection, then evaluation."
            note="Lower scores are better"
          />
          <div
            className="record-table-scroll"
            role="region"
            tabIndex={0}
            aria-label="Research season metrics"
          >
            <table>
              <caption>
                Selected recipe across earlier-season folds and final 2026. Select a season to
                inspect calibration and forecasts.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Season</th>
                  <th scope="col">Scope</th>
                  <th scope="col">Picks</th>
                  <th scope="col">Accuracy</th>
                  <th scope="col">Brier ↓</th>
                  <th scope="col">Log loss ↓</th>
                </tr>
              </thead>
              <tbody>
                {w.seasons.map((s) => (
                  <tr key={s.season} className={season === s.season ? 'selected' : ''}>
                    <th scope="row">
                      <button
                        aria-pressed={season === s.season}
                        aria-label={`Inspect ${s.season} research evidence`}
                        onClick={() => setSeason(s.season)}
                      >
                        {s.season}
                        <span aria-hidden="true">↗</span>
                      </button>
                    </th>
                    <td>{s.phase === 'final' ? 'Final' : 'Selection'}</td>
                    <td>
                      {s.metrics.correct}/{s.metrics.n}
                    </td>
                    <td>{percent(s.metrics.accuracy)}</td>
                    <td>{s.metrics.brier.toFixed(4)}</td>
                    <td>{s.metrics.logLoss.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ServiceNote>
            The {percent(w.macroValidationAccuracy, 2)} selection score averages four season
            accuracies. It is not the final-season accuracy or a pooled future guarantee.
          </ServiceNote>
          <div className="record-baseline-table">
            <h3>2026 / matched baselines</h3>
            <div
              className="record-table-scroll"
              tabIndex={0}
              role="region"
              aria-label="Final research baseline comparison"
            >
              <table>
                <caption>All three predictors cover the same 70 eligible matches.</caption>
                <MetricsHead />
                <tbody>
                  <MetricsRow name="Selected forest" metrics={final.metrics} />
                  <MetricsRow
                    name="Always chase"
                    metrics={w.baselines.neutral_50_percent_ties_choose_chase}
                    note="50/50 probabilities; chase at tie"
                  />
                  <MetricsRow
                    name="Prior batting-order history"
                    metrics={w.baselines.prior_order_history}
                  />
                </tbody>
              </table>
            </div>
          </div>
          <details className="record-exact">
            <summary>Paired comparison uncertainty</summary>
            <p>
              Positive gain favors the selected model. Date-cluster intervals cross zero and omit
              some season/team and selection uncertainty.
            </p>
            <GainReadout
              label="Brier gain vs always chase"
              value={w.pairedGains.neutral_50_percent_ties_choose_chase.brier}
            />
            <GainReadout
              label="Log-loss gain vs order history"
              value={w.pairedGains.prior_order_history.log_loss}
            />
            <p>
              Model alone correct: {w.discordance.model_only_correct}. Chase alone correct:{' '}
              {w.discordance.chase_only_correct}.
            </p>
          </details>
        </section>
        <section className="record-chart-panel">
          <Heading
            number="03 / Probability calibration"
            title="Forecast against outcome."
            note={`${season} / ${current.metrics.n} matches`}
          />
          <p className="record-context">
            {current.phase === 'final' ? 'Final retrospective cohort' : 'Selection-fold cohort'} ·
            batting-first outcome · ten fixed 10% bins, empty bins omitted.
          </p>
          <CalibrationChart
            key={season}
            metrics={current.metrics}
            label={`${season} direct winner research`}
          />
          <div className="record-ece">
            <span>Weighted bin calibration error</span>
            <b className="mono">{(current.metrics.ece * 100).toFixed(2)} pp</b>
          </div>
          <ServiceNote>
            Small bins are noisy. Calibration error is not the percentage of matches predicted
            incorrectly. Bin intervals do not capture every source of dependence or model
            uncertainty.
          </ServiceNote>
        </section>
      </div>
      <ForecastLedger key={season} season={season} />
    </>
  );
}

const variantLabels: Record<SimulatorVariant, string> = {
  population: 'Population only',
  participant_raw: 'Player model / raw',
  participant_delivery_corrected: 'Player model / delivery correction',
};
function SimulatorEvidence() {
  const [year, setYear] = useState(2026),
    [variant, setVariant] = useState<SimulatorVariant>('participant_raw');
  const sim = data.simulator,
    season = sim.seasons.find((s) => s.season === year)!,
    evaluation = season.variants[variant],
    score = variant === 'participant_delivery_corrected' ? null : season.scores[variant];
  return (
    <>
      <div className="record-scope-banner">
        <div>
          <span className="eyebrow">Full two-innings simulator / retrospective diagnostics</span>
          <h2>Precision is not accuracy.</h2>
          <p>
            {sim.trials} simulations per match and variant. More draws reduce sampling noise; they
            do not establish useful winner forecasts.
          </p>
        </div>
        <div className="record-cohort-count">
          <strong>{sim.eligible}</strong>
          <span>
            format-eligible matches
            <br />
            2024–2026
          </span>
        </div>
      </div>
      <div className="record-sim-controls">
        <div className="filter-group" aria-label="Simulator evaluation season">
          {sim.seasons.map((s) => (
            <TagToggle key={s.season} active={year === s.season} onClick={() => setYear(s.season)}>
              {s.season}
            </TagToggle>
          ))}
        </div>
        <div className="filter-group" aria-label="Simulator variant">
          {(Object.keys(variantLabels) as SimulatorVariant[]).map((v) => (
            <TagToggle key={v} active={variant === v} onClick={() => setVariant(v)}>
              {variantLabels[v]}
            </TagToggle>
          ))}
        </div>
      </div>
      <div className="record-scope-note">
        <b>
          {variantLabels[variant]} / {year}
        </b>
        <p>
          {variant === 'population'
            ? 'Uses prior deliveries and known post-toss ground/order, without individual player effects.'
            : 'Conditions on recorded post-match participant pools and hypothetical prior-only tactics. These are not timestamp-verified announced-XI forecasts.'}{' '}
          {variant === 'participant_delivery_corrected'
            ? 'The optional delivery correction remains off by default.'
            : ''}
        </p>
      </div>
      <div className="record-main-grid">
        <section className="record-seasons">
          <Heading
            number="01 / Winner evaluation"
            title="Against simple baselines."
            note={`${evaluation.metrics.n} matches`}
          />
          <div
            className="record-table-scroll"
            tabIndex={0}
            role="region"
            aria-label="Simulator winner metrics"
          >
            <table>
              <caption>
                {year}, {variantLabels[variant]}; identical cohort within this table
              </caption>
              <MetricsHead />
              <tbody>
                <MetricsRow name={variantLabels[variant]} metrics={evaluation.metrics} />
                <MetricsRow name="Neutral 50/50" metrics={evaluation.neutral} />
                <MetricsRow name="Prior batting-order history" metrics={evaluation.orderBaseline} />
              </tbody>
            </table>
          </div>
          <ServiceNote>
            Simulator threshold accuracy gives half credit at exactly 50%. Win probabilities
            condition on decisive trials. This differs from the deterministic chase-at-tie rule in
            winner research.
          </ServiceNote>
          <GainReadout label="Brier gain vs neutral" value={evaluation.gain.brier} />
          <GainReadout label="Log-loss gain vs neutral" value={evaluation.gain.log_loss} />
          <p className="record-footnote">
            Positive favors this variant. {pairedGainNote(Object.values(evaluation.gain))} These 95%
            date-cluster intervals omit some season/team and model uncertainty.
          </p>
        </section>
        <section className="record-chart-panel">
          <Heading
            number="02 / Win calibration"
            title="Keep the cohort visible."
            note={`${year} / ${evaluation.metrics.n} matches`}
          />
          <CalibrationChart
            key={`${year}-${variant}`}
            metrics={evaluation.metrics}
            label={`${year} ${variantLabels[variant]} simulator`}
          />
        </section>
      </div>
      {score ? (
        <section className="score-audit">
          <Heading
            number="03 / First-innings uncertainty"
            title="Better coverage. Wider intervals."
            note="Nominal 90% score interval"
          />
          <p className="record-context">
            2024-fitted score correction · diagnostic only · not enabled in serving · same{' '}
            {score.raw.n} innings in both rows.
          </p>
          <div className="score-comparison">
            {(
              [
                ['Raw', score.raw],
                ['Frozen score correction', score.candidate],
              ] as const
            ).map(([label, m]) => (
              <div className="score-evidence" key={label}>
                <h3>{label}</h3>
                <div className="coverage-value">
                  <strong>{percent(m.coverage)}</strong>
                  <span>
                    {m.covered}/{m.n} scores covered
                  </span>
                </div>
                <div
                  className="coverage-track"
                  role="img"
                  aria-label={`${percent(m.coverage)} empirical coverage; target 90 percent`}
                >
                  <span style={{ width: percent(m.coverage) }} />
                  <i style={{ left: '90%' }} />
                </div>
                <span className="mono">
                  Approx. 95% coverage interval {percent(m.interval.lower)}–
                  {percent(m.interval.upper)}
                </span>
                <dl>
                  <div>
                    <dt>Mean 90% width</dt>
                    <dd>{m.width.toFixed(1)} runs</dd>
                  </div>
                  <div>
                    <dt>Mean absolute error ↓</dt>
                    <dd>{m.mae.toFixed(2)} runs</dd>
                  </div>
                  <div>
                    <dt>90% interval score ↓</dt>
                    <dd>{m.intervalScore.toFixed(2)}</dd>
                  </div>
                </dl>
              </div>
            ))}
          </div>
          <div className="score-audit-notes">
            <div>
              <GainReadout label="MAE improvement / runs" value={score.maeGain} />
              <GainReadout label="Interval-score improvement" value={score.intervalGain} />
            </div>
            <ServiceNote>
              Interval score penalizes width and missed outcomes. Coverage alone can improve by
              widening intervals. This correction changes score summaries, not winner probabilities
              or physical match simulations. Coverage intervals assume independent cases
              approximately; paired gains omit fit/selection uncertainty.
            </ServiceNote>
          </div>
        </section>
      ) : (
        <section className="score-audit">
          <Heading
            number="03 / First-innings uncertainty"
            title="No score audit for this variant."
          />
          <p className="record-context">
            The saved score-calibration audit covers the raw player and population variants. Select
            one of those above to inspect its paired score correction; no missing audit is inferred.
          </p>
        </section>
      )}
      <section className="record-cohorts">
        <Heading number="04 / Cohort accounting" title="Different screens. Different totals." />
        <dl>
          {(Object.keys(sim.cohorts) as SimulatorVariant[]).map((v) => (
            <div key={v}>
              <dt>{variantLabels[v]}</dt>
              <dd>{sim.cohorts[v]} forecasts</dd>
            </div>
          ))}
          <div>
            <dt>Format/result exclusions</dt>
            <dd>{sim.formatExclusions.length} matches</dd>
          </div>
          <div>
            <dt>Unsupported participant pools</dt>
            <dd>{sim.poolExclusions.length} matches</dd>
          </div>
        </dl>
        <p>
          Totals span development 2024 and evaluation 2025–2026. Delivery-corrected forecasts begin
          in 2025. In 2026, population has 70 matches and player variants have 67; comparing those
          headline accuracies directly would mix cohorts. None is a verified historical XI benefit
          test.
        </p>
        <details className="record-exact">
          <summary>Excluded match references and reasons</summary>
          <ul>
            {[...sim.formatExclusions, ...sim.poolExclusions].map((p) => (
              <li key={p.match_id}>
                <b className="mono">{p.match_id}</b> · {p.reason.replaceAll('_', ' ')}
              </li>
            ))}
          </ul>
        </details>
      </section>
    </>
  );
}

function DeliveryEvidence() {
  const d = data.delivery;
  return (
    <>
      <div className="record-scope-banner">
        <div>
          <span className="eyebrow">Legal-delivery model / optional correction</span>
          <h2>One delivery is not a match.</h2>
          <p>
            Three frozen offsets fitted to {d.fitDeliveries.toLocaleString()} date-blocked 2024
            legal deliveries. Evidence before {formatDate(d.fitCutoff)}; evaluation in 2025 and
            2026.
          </p>
        </div>
        <div className="record-cohort-count">
          <strong>03</strong>
          <span>
            joint-event offsets
            <br />
            off by default
          </span>
        </div>
      </div>
      <section className="delivery-audit">
        <Heading
          number="01 / Joint log loss"
          title="Small changes. Uncertain gains."
          note="Lower loss is better"
        />
        <div
          className="record-table-scroll"
          tabIndex={0}
          role="region"
          aria-label="Delivery loss audit"
        >
          <table>
            <caption>Same legal deliveries within each year's raw/corrected pair</caption>
            <thead>
              <tr>
                <th scope="col">Season</th>
                <th scope="col">Deliveries</th>
                <th scope="col">Matches</th>
                <th scope="col">Raw loss ↓</th>
                <th scope="col">Corrected ↓</th>
                <th scope="col">Gain / 95% match-cluster interval</th>
              </tr>
            </thead>
            <tbody>
              {d.seasons.map((s) => (
                <tr key={s.season}>
                  <th scope="row">{s.season}</th>
                  <td>{s.raw.n.toLocaleString()}</td>
                  <td>{s.raw.matches}</td>
                  <td>{s.raw.loss.toFixed(6)}</td>
                  <td>{s.corrected.loss.toFixed(6)}</td>
                  <td className="delivery-gain">
                    <b>{signedMetric(s.gain.mean, 6)}</b>
                    <span>
                      {signedMetric(s.gain.lower, 6)} to {signedMetric(s.gain.upper, 6)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ServiceNote>
          Both paired intervals cross zero. A robust overall joint-loss improvement is not
          demonstrated. Later seasons were previously inspected for other diagnostics; this is not
          prospective validation.
        </ServiceNote>
      </section>
      <div className="delivery-year-grid">
        {d.seasons.map((s) => (
          <section key={s.season} className="delivery-events">
            <Heading
              number={`${s.season} / Event calibration`}
              title="Mixed by event."
              note="Weighted bin error / pp"
            />
            <div
              className="record-table-scroll"
              tabIndex={0}
              role="region"
              aria-label={`${s.season} event calibration errors`}
            >
              <table>
                <caption>
                  Ten-bin expected calibration error in percentage points; lower is better
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Event</th>
                    <th scope="col">Raw</th>
                    <th scope="col">Corrected</th>
                  </tr>
                </thead>
                <tbody>
                  {(
                    [
                      ['boundary', 'Boundary'],
                      ['dot', 'Zero batter runs'],
                      ['striker_dismissal', 'Striker dismissal'],
                    ] as const
                  ).map(([key, label]) => (
                    <tr key={key}>
                      <th scope="row">{label}</th>
                      <td>{(s.raw.events[key].ece * 100).toFixed(2)}</td>
                      <td>{(s.corrected.events[key].ece * 100).toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="record-footnote">
              Boundary calibration improves; zero-run and dismissal results are mixed. These are
              calibration errors, not percentages of deliveries predicted incorrectly.
            </p>
          </section>
        ))}
      </div>
      <section className="record-method">
        <Heading number="02 / Serving status" title="A challenger, not a promotion." />
        <p>
          The joint correction preserves normalized event probabilities. It is available as an
          explicit experimental option, and remains off in the default Match/Lab workflow. It does
          not fit score pressure, weather, extras or match-win calibration. Calibration-coefficient
          uncertainty is not propagated; raw posterior credible intervals are not reused as
          corrected intervals.
        </p>
        <ServiceNote>
          Delivery-level calibration cannot establish reliable full-match win estimates or
          counterfactual XI improvements.
        </ServiceNote>
      </section>
    </>
  );
}

function EvidenceReceipt({ view }: { view: EvidenceView }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="evidence-receipt">
      <Heading
        number="05 / Evidence receipt"
        title="Saved results. Traceable sources."
        note="No live accuracy feed"
      />
      <div className="evidence-receipt-grid">
        <div>
          <p>
            Record reads the project's saved reports. It does not retrain a model, run a new
            backtest, or change Match/Lab defaults.
          </p>
          <dl>
            <div>
              <dt>Extract saved</dt>
              <dd>{formatDate(data.exportedAt.slice(0, 10))}</dd>
            </div>
            <div>
              <dt>Winner artifact checks</dt>
              <dd>{data.winner.integrityChecks.toLocaleString()} passed</dd>
            </div>
            <div>
              <dt>Simulator artifact checks</dt>
              <dd>{data.simulator.integrityChecks.toLocaleString()} passed</dd>
            </div>
            <div>
              <dt>Source database</dt>
              <dd className="source-hash mono">{data.databaseSha256}</dd>
            </div>
          </dl>
          <ServiceNote>
            Passed checks verify artifacts and temporal integrity. They do not mean that prediction
            accuracy passed, that a model is decision-ready, or that a recommended XI improves
            outcomes.
          </ServiceNote>
        </div>
        <div className="record-receipt-actions">
          <button
            className="yellow-button"
            onClick={() => downloadEvidence('concourse-research-record.json', data)}
          >
            Save evidence extract <Icon name="arrow" />
          </button>
          <button className="text-button" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            Source files and SHA-256 {open ? '−' : '+'}
          </button>
          <p className="record-footnote">
            Download includes all displayed cohorts and the complete 353-row research ledger.
            Filtering does not change the evidence extract.
          </p>
          <span className="record-status">Production validation not established</span>
        </div>
      </div>
      {open && (
        <ul className="record-sources">
          {data.sources.map((s) => (
            <li key={s.path}>
              <span>{s.path}</span>
              <code>{s.sha256}</code>
            </li>
          ))}
        </ul>
      )}
      <details className="record-exact">
        <summary>Source limitations for this evidence view</summary>
        <ul>
          {data[
            view === 'winner' ? 'winner' : view === 'simulator' ? 'simulator' : 'delivery'
          ].limitations.map((l, i) => (
            <li key={i}>{l.replaceAll('_', ' ')}</li>
          ))}
        </ul>
      </details>
    </section>
  );
}

export default function RecordWorkspace({
  theme,
  onTheme,
}: {
  theme: string;
  onTheme: () => void;
}) {
  const [view, setView] = useState<EvidenceView>('winner');
  if (!valid)
    return (
      <main className="concourse record-workspace" id="record-content" tabIndex={-1}>
        <div className="record-empty" role="alert">
          <h1>Evidence unavailable.</h1>
          <p>
            The saved extract failed its consistency checks. Re-export it from the source reports
            before displaying results.
          </p>
        </div>
      </main>
    );
  return (
    <main className="concourse record-workspace" id="record-content" tabIndex={-1}>
      <header className="record-header">
        <div>
          <span className="eyebrow">The Concourse / 04 / Evidence</span>
          <h1>
            Record <span aria-hidden="true">↙</span>
          </h1>
          <p>What the models actually measured.</p>
        </div>
        <div className="record-header-key">
          <Icon name="stumps" />
          <span className="eyebrow">Retrospective research</span>
          <strong>
            Read the result.
            <br />
            Keep the limits.
          </strong>
          <span>Saved project evidence · not live predictions</span>
        </div>
        <button
          className="record-theme icon-button"
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          onClick={onTheme}
        >
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
        </button>
      </header>
      <div className="record-evidence-nav" aria-label="Evidence view">
        {(
          [
            ['winner', '01', 'Winner research'],
            ['simulator', '02', 'Match simulator'],
            ['delivery', '03', 'Delivery model'],
          ] as const
        ).map(([key, number, label]) => (
          <button
            key={key}
            className={view === key ? 'selected' : ''}
            aria-pressed={view === key}
            onClick={() => setView(key)}
          >
            <span className="evidence-view-number mono">{number}</span>
            <span>{label}</span>
            <span aria-hidden="true">↗</span>
          </button>
        ))}
      </div>
      <div className="record-saved-strip">
        <span className="source-dot" />
        <span>Saved research extract</span>
        <span className="mono">
          {view === 'winner'
            ? 'Winner challenger / not in planning defaults'
            : view === 'simulator'
              ? 'Full-match engine / not match-level calibrated'
              : 'Delivery correction / experimental, off by default'}
        </span>
      </div>
      {view === 'winner' ? (
        <WinnerEvidence />
      ) : view === 'simulator' ? (
        <SimulatorEvidence />
      ) : (
        <DeliveryEvidence />
      )}
      <EvidenceReceipt view={view} />
      <footer className="page-footer">
        <span>The Concourse / IPL research</span>
        <span className="mono">Evidence edition · 04</span>
      </footer>
    </main>
  );
}
