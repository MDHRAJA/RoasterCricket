import { useEffect, useRef, useState } from 'react';
import type { ArchiveMatch, DataSource } from '../api/contracts';
import {
  exampleRequest,
  parseSimulationRequest,
  savedRun,
  savedScenario,
  type CompletedRun,
  type SimulationRequest,
} from '../api/simulation';
import { formatDate, shortGround } from '../domain/archive';
import { percent, sameRequest, validateArchiveContext } from '../domain/simulation';
import { team } from '../domain/teams';
import { useSimulation } from '../useSimulation';
import { MatchRecord } from './Dialogs';
import { OverLine, SampleScorecard, ScoreDistributions, VerdictBoard } from './SimulationCharts';
import { Icon, RouteBullet, ServiceNote, TagToggle } from './Signs';
import '../match.css';
import type { LabSlot } from '../domain/lab';

const initialNames: Record<string, string> = savedScenario.players;
function usePlayerNames(request: SimulationRequest | null) {
  const [names, setNames] = useState<Record<string, string>>(initialNames);
  const a = request?.team_a.team_id,
    b = request?.team_b.team_id;
  useEffect(() => {
    if (!a || !b) return;
    const controller = new AbortController(),
      timer = window.setTimeout(() => controller.abort(), 3000);
    const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');
    Promise.allSettled(
      [a, b].map(async (id) => {
        const response = await fetch(`${base}/teams/${encodeURIComponent(id)}/roster?season=2026`, {
          signal: controller.signal,
        });
        if (!response.ok) return;
        const data = await response.json();
        if (!Array.isArray(data.data?.members)) return;
        const labels: Record<string, string> = {};
        for (const member of data.data.members)
          if (
            typeof member.player?.player_id === 'string' &&
            typeof member.player?.display_name === 'string'
          )
            labels[member.player.player_id] = member.player.display_name;
        if (!controller.signal.aborted) setNames((previous) => ({ ...previous, ...labels }));
      }),
    ).finally(() => window.clearTimeout(timer));
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [a, b]);
  return names;
}

function saveJson(value: unknown, name: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2) + '\n'], { type: 'application/json' }),
  );
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function SuppliedPlans({
  request,
  names,
}: {
  request: SimulationRequest;
  names: Record<string, string>;
}) {
  const [side, setSide] = useState(0),
    plans = [request.team_a, request.team_b],
    plan = plans[side];
  return (
    <section className="supplied-plans">
      <div className="panel-caption">
        <h2>05 / Supplied XI</h2>
        <span>Scenario input</span>
      </div>
      <div className="plan-selector">
        {plans.map((p, i) => (
          <TagToggle active={i === side} onClick={() => setSide(i)} key={p.team_id}>
            {p.team_id}
          </TagToggle>
        ))}
      </div>
      <p className="plan-note">Batting order · supplied, not optimized</p>
      <ol className="plan-order">
        {plan.batting_order.map((id, index) => (
          <li key={id}>
            <span className="mono">{String(index + 1).padStart(2, '0')}</span>
            <strong>{names[id] || id}</strong>
            {plan.captain_id === id && (
              <abbr title="Supplied captain; not a predictive input">C</abbr>
            )}
          </li>
        ))}
      </ol>
      <details className="bowling-plan">
        <summary>20-over bowling plan</summary>
        <ol>
          {plan.bowling_plan.map((id, index) => (
            <li key={index}>
              <span className="mono">{String(index + 1).padStart(2, '0')}</span>
              <span>{names[id] || id}</span>
            </li>
          ))}
        </ol>
      </details>
      {plan.impact && (
        <p className="plan-impact">
          Interval Impact: {names[plan.impact.outgoing_id] || plan.impact.outgoing_id} →{' '}
          {names[plan.impact.incoming_id] || plan.impact.incoming_id}
        </p>
      )}
      <ServiceNote>
        Saved roster membership and match-day eligibility are different. This XI is a planning
        input.
      </ServiceNote>
    </section>
  );
}

function RunReceipt({ run }: { run: CompletedRun }) {
  const result = run.response.data,
    training = result.training,
    exposures = result.reliability.evidence?.simulated_legal_delivery_exposures;
  const notes = [...new Set([...result.assumptions, ...run.response.meta.warnings])];
  return (
    <aside className="run-receipt" aria-labelledby="receipt-title">
      <div className="panel-caption">
        <h2 id="receipt-title">Run receipt</h2>
        <span className="receipt-number">R{run.request.seed}</span>
      </div>
      <div className="receipt-status">
        <span className="eyebrow">Model status</span>
        <h3>Experimental.</h3>
        <p>Match-win probabilities are not historically calibrated.</p>
      </div>
      <dl>
        <div>
          <dt>Evidence before</dt>
          <dd>{formatDate(training.exclusive_cutoff)}</dd>
        </div>
        <div>
          <dt>Latest match in training</dt>
          <dd>
            {training.last_included_date ? formatDate(training.last_included_date) : 'Not recorded'}
          </dd>
        </div>
        <div>
          <dt>Recorded deliveries</dt>
          <dd className="mono">{training.recorded_deliveries.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Trials / seed</dt>
          <dd className="mono">
            {result.simulations} / {result.seed}
          </dd>
        </div>
        <div>
          <dt>Source</dt>
          <dd>{run.source === 'saved' ? 'Saved project run' : 'Local simulation API'}</dd>
        </div>
        <div>
          <dt>Player availability</dt>
          <dd>
            {run.request.allow_unknown_availability
              ? 'Unknown assumed'
              : 'Checked against dated records'}
          </dd>
        </div>
        <div>
          <dt>Eligibility</dt>
          <dd>{result.eligibility_verified ? 'Verified by service' : 'Unverified'}</dd>
        </div>
        <div>
          <dt>Delivery model</dt>
          <dd>
            {run.request.use_delivery_calibration
              ? 'Optional correction candidate'
              : 'Raw model default'}
          </dd>
        </div>
      </dl>
      {exposures && (
        <div className="exposure-note">
          <strong className="mono">{percent(exposures.no_direct_history_fraction)}</strong>
          <p>
            of sampled legal deliveries had no direct batter–bowler history. Population evidence
            supplied the fallback.
          </p>
        </div>
      )}
      <details className="model-notes">
        <summary>
          Assumptions & limitations <span className="mono">{notes.length}</span>
        </summary>
        <ul>
          {notes.map((note) => (
            <li key={note}>{note.replaceAll('_', ' ')}</li>
          ))}
        </ul>
        <p className="model-version mono">{result.simulator_version}</p>
      </details>
      <div className="receipt-downloads">
        <button
          className="text-button"
          onClick={() => saveJson(run.request, 'concourse-request.json')}
        >
          Save request <span aria-hidden="true">↓</span>
        </button>
        <button
          className="text-button"
          onClick={() =>
            saveJson(
              {
                request: run.request,
                response: run.response,
                source: run.source,
                completed_at: run.completedAt,
              },
              'concourse-run.json',
            )
          }
        >
          Save full run <span aria-hidden="true">↓</span>
        </button>
      </div>
    </aside>
  );
}

export default function MatchWorkspace({
  match,
  example,
  missing,
  source,
  onBack,
  onExample,
  theme,
  onTheme,
  scenario,
  scenarioLabel,
  expiredScenario = false,
  backLabel = 'Fixtures',
  onEditLab,
  onScenarioRun,
}: {
  match?: ArchiveMatch;
  example: boolean;
  missing: boolean;
  source: DataSource;
  onBack: () => void;
  onExample: () => void;
  theme: string;
  onTheme: () => void;
  scenario?: LabSlot;
  scenarioLabel?: string;
  expiredScenario?: boolean;
  backLabel?: string;
  onEditLab?: (
    request: SimulationRequest,
    run: CompletedRun | null,
    names: Record<string, string>,
    ground: string,
  ) => void;
  onScenarioRun?: (run: CompletedRun) => void;
}) {
  const initialRequest = scenario?.request || (example ? exampleRequest : null);
  const [baseRequest, setBaseRequest] = useState<SimulationRequest | null>(initialRequest);
  const [trials, setTrials] = useState(initialRequest?.simulations ?? exampleRequest.simulations),
    [seed, setSeed] = useState(String(initialRequest?.seed ?? exampleRequest.seed));
  const [assumeAvailability, setAssumeAvailability] = useState(
    initialRequest?.allow_unknown_availability ?? exampleRequest.allow_unknown_availability,
  );
  const [json, setJson] = useState(''),
    [importError, setImportError] = useState(''),
    [factsOpen, setFactsOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null),
    heading = useRef<HTMLHeadingElement>(null);
  const simulation = useSimulation(scenario ? scenario.run : example ? savedRun : null),
    { state } = simulation;
  const submitted = state.run;
  const synced = useRef(scenario?.run?.completedAt || null);
  useEffect(() => {
    if (
      submitted?.source === 'api' &&
      submitted.completedAt &&
      synced.current !== submitted.completedAt
    ) {
      synced.current = submitted.completedAt;
      onScenarioRun?.(submitted);
    }
  }, [submitted, onScenarioRun]);
  const busy = state.phase === 'running';
  const validSeed =
    /^\d+$/.test(seed) && Number.isInteger(Number(seed)) && Number(seed) <= 4294967295;
  const draft = baseRequest
    ? {
        ...baseRequest,
        simulations: trials,
        seed: Number(seed),
        allow_unknown_availability: assumeAvailability,
      }
    : null;
  const changed = Boolean(submitted && draft && !sameRequest(submitted.request, draft));
  const displayRequest = submitted?.request || baseRequest;
  const apiNames = usePlayerNames(displayRequest);
  const names = { ...apiNames, ...scenario?.names };
  const ids = match
    ? [match.team1_id, match.team2_id]
    : [
        initialRequest?.team_a.team_id || exampleRequest.team_a.team_id,
        initialRequest?.team_b.team_id || exampleRequest.team_b.team_id,
      ];
  const ground = match
    ? shortGround(match)
    : scenario?.venueName || savedScenario.venue.name.split(',')[0];
  function run() {
    if (draft && validSeed && !busy) simulation.run(parseSimulationRequest(draft));
  }
  function apply(raw: string) {
    try {
      if (raw.length > 65536) throw new Error('Use a scenario request smaller than 64 KB.');
      const request = parseSimulationRequest(JSON.parse(raw));
      validateArchiveContext(
        request,
        match || {
          season: 2026,
          team1_id: initialRequest?.team_a.team_id || exampleRequest.team_a.team_id,
          team2_id: initialRequest?.team_b.team_id || exampleRequest.team_b.team_id,
          venue_id: initialRequest?.venue_id || exampleRequest.venue_id,
          match_date: '2099-12-31',
        },
      );
      simulation.clear();
      setBaseRequest(request);
      setTrials(request.simulations);
      setSeed(String(request.seed));
      setAssumeAvailability(request.allow_unknown_availability);
      setImportError('');
      setJson('');
    } catch (e) {
      setImportError(
        e instanceof SyntaxError
          ? 'The request is not valid JSON. Check its formatting and try again.'
          : e instanceof Error
            ? e.message
            : 'The request is not valid JSON.',
      );
    }
  }
  useEffect(() => {
    heading.current?.focus();
  }, []);
  useEffect(() => {
    const keyboard = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (
        e.code === 'Space' &&
        !e.repeat &&
        !e.metaKey &&
        !e.ctrlKey &&
        !e.altKey &&
        !target.closest('button,input,textarea,select,summary,a,[contenteditable]') &&
        !document.querySelector('dialog[open]')
      ) {
        e.preventDefault();
        if (!busy) run();
      }
    };
    window.addEventListener('keydown', keyboard);
    return () => window.removeEventListener('keydown', keyboard);
  });
  if (!example && !scenario && !match)
    return (
      <main className="concourse match-workspace" id="match-content" tabIndex={-1}>
        <div className="empty-state">
          <div className="missing-match-toolbar">
            <span className="eyebrow">02 / Match</span>
            <button
              className="icon-button"
              onClick={onTheme}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            >
              <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
            </button>
          </div>
          <h1>
            {expiredScenario
              ? 'Scenario session ended'
              : missing
                ? 'Record not found'
                : 'Opening archive'}
          </h1>
          <p>
            {expiredScenario
              ? 'Lab drafts reset when this page is reloaded. Open Lab to start another plan. Save a scenario request before reloading to keep a copy.'
              : missing
                ? 'This reference is not in the selected season.'
                : 'Retrieving the selected record.'}
          </p>
          <button className="text-button" onClick={onBack}>
            ← Back to {backLabel}
          </button>
        </div>
      </main>
    );
  return (
    <main className="concourse match-workspace" id="match-content" tabIndex={-1}>
      <header className="platform-header">
        <div className="platform-wayfinding">
          <button onClick={onBack}>← {backLabel}</button>
          <span className="eyebrow">02 / Match</span>
          {baseRequest && (
            <button
              className="jump-controls"
              onClick={() => {
                document.getElementById('run-controls')?.focus();
                document.getElementById('run-controls')?.scrollIntoView({ block: 'start' });
              }}
            >
              Run setup ↓
            </button>
          )}
          <button
            className="platform-theme icon-button"
            onClick={onTheme}
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          >
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
          </button>
        </div>
        <div className="platform-identity">
          <div className="platform-teams">
            <div className="platform-bullets">
              <RouteBullet id={ids[0]} />
              <RouteBullet id={ids[1]} />
            </div>
            <h1 ref={heading} tabIndex={-1}>
              {ids[0]}
              <span> v </span>
              {ids[1]}
            </h1>
            <p>
              {team(ids[0]).name} / {team(ids[1]).name}
            </p>
          </div>
          <div className="platform-ground">
            <Icon name="pitch" />
            <div>
              <span className="eyebrow">
                {example || scenario
                  ? 'Hypothetical planning scenario'
                  : 'Archive replay workspace'}
              </span>
              <strong>{ground}</strong>
              <span>
                {match
                  ? `${formatDate(match.match_date)} · Recorded match`
                  : scenario
                    ? scenarioLabel
                    : savedScenario.venue.city}
              </span>
            </div>
          </div>
        </div>
        <div className="platform-context">
          <span className="solid-tag">
            {example || scenario
              ? scenarioLabel
                ? `${scenarioLabel} · hypothetical`
                : 'Scenario · not a fixture'
              : 'Hypothetical replay · not an historical forecast'}
          </span>
          {match ? (
            <button className="text-button" onClick={() => setFactsOpen(true)}>
              View recorded result <Icon name="arrow" />
            </button>
          ) : (
            <span>
              2026 rule profile · {displayRequest?.batting_first_team_id || 'CSK'} bats first
            </span>
          )}
        </div>
      </header>
      {baseRequest ? (
        <section
          className="run-controls"
          id="run-controls"
          tabIndex={-1}
          aria-label="Run a match simulation"
        >
          <div className="run-control-setting">
            <span className="eyebrow">Simulations</span>
            <div className="filter-group">
              {[50, 200, 500, 1000].map((n) => (
                <TagToggle
                  active={trials === n}
                  key={n}
                  disabled={busy}
                  onClick={() => setTrials(n)}
                >
                  {n.toLocaleString()}
                </TagToggle>
              ))}
            </div>
            <span className="control-helper">
              {![50, 200, 500, 1000].includes(trials)
                ? `${trials} trials from imported request`
                : '50–1,000 trials per run'}
            </span>
          </div>
          <label className="seed-control">
            <span className="eyebrow">Reproducible seed</span>
            <input
              inputMode="numeric"
              value={seed}
              disabled={busy}
              onChange={(e) => setSeed(e.target.value)}
              aria-invalid={!validSeed}
              aria-describedby="seed-help"
            />
            <span className="control-helper" id="seed-help">
              {validSeed ? 'Same inputs, seed and dataset' : 'Enter 0–4,294,967,295'}
            </span>
          </label>
          <div className="run-action">
            <button
              className="yellow-button"
              onClick={busy ? simulation.cancel : run}
              disabled={!busy && !validSeed}
            >
              {busy ? 'Stop waiting' : 'Run simulation'}
              <Icon name={busy ? 'close' : 'arrow'} />
            </button>
            <span className="mono">
              {busy ? 'Awaiting the complete run' : 'SPACE / Run simulation'}
            </span>
          </div>
          <label className="availability-control">
            <input
              type="checkbox"
              checked={assumeAvailability}
              disabled={busy}
              onChange={(e) => setAssumeAvailability(e.target.checked)}
            />
            <span>Assume unknown player availability for this planning scenario.</span>
          </label>
          {onEditLab && draft && (
            <button
              className="text-button edit-lab-link"
              disabled={busy || !validSeed}
              onClick={() => onEditLab(parseSimulationRequest(draft), submitted, names, ground)}
            >
              Edit team plans in Lab <Icon name="arrow" />
            </button>
          )}
        </section>
      ) : (
        <section className="scenario-empty">
          <span className="empty-number">—</span>
          <div>
            <h2>
              {match?.season === 2025
                ? 'Simulation profile unavailable for 2025'
                : 'No scenario loaded'}
            </h2>
            <p>
              {match?.season === 2025
                ? 'The archive remains available. The current simulator uses the 2026 planning profile.'
                : 'A simulation requires explicit starting XIs, batting orders and bowling plans. Recorded participants are not automatically treated as a confirmed XI.'}
            </p>
            <button className="text-button" onClick={onExample}>
              Open CSK v MI example <Icon name="arrow" />
            </button>
          </div>
        </section>
      )}
      <div
        className={`run-status ${state.phase === 'failed' ? 'has-error' : ''}`}
        role="status"
        aria-live="polite"
      >
        <span className="status-square" />
        <div>
          <strong>
            {busy
              ? 'Simulation in progress'
              : state.phase === 'failed'
                ? 'Run not completed'
                : state.phase === 'ready' && state.notice
                  ? 'Stopped waiting'
                  : changed
                    ? 'Inputs changed'
                    : submitted
                      ? submitted.source === 'saved'
                        ? 'Saved run displayed'
                        : 'New run complete'
                      : baseRequest
                        ? 'Scenario loaded · ready to run'
                        : 'Waiting for an explicit scenario'}
          </strong>
          <span>
            {busy
              ? `Computing the submitted scenario. ${submitted ? 'Previous results remain below.' : 'Results appear when the run finishes.'}`
              : state.phase === 'failed'
                ? state.error.message
                : state.phase === 'ready' && state.notice
                  ? state.notice
                  : changed
                    ? 'Results below still use the previous submitted inputs. Run again to update them.'
                    : submitted
                      ? `${submitted.request.simulations} trials · seed ${submitted.request.seed} · evidence before ${formatDate(submitted.request.as_of)}`
                      : baseRequest
                        ? 'Run the supplied scenario to produce estimates.'
                        : 'Load a request below or open the saved planning example.'}
          </span>
          {state.phase === 'failed' && state.error.details.length > 0 && (
            <ul>
              {state.error.details.map((detail, index) => (
                <li key={index}>{detail}</li>
              ))}
            </ul>
          )}
        </div>
        {submitted && (
          <span className="run-source-tag">
            {submitted.source === 'saved' ? 'Saved output' : 'API output'}
          </span>
        )}
      </div>
      {submitted ? (
        <>
          <div className="match-wall">
            <div className="match-main-column">
              <VerdictBoard run={submitted} />
              <ScoreDistributions run={submitted} />
            </div>
            <div className="match-aside-column">
              <RunReceipt run={submitted} />
              <SuppliedPlans
                key={JSON.stringify(submitted.request)}
                request={submitted.request}
                names={names}
              />
            </div>
          </div>
          {submitted.response.data.sample_match && (
            <OverLine
              key={`${submitted.request.seed}-${submitted.completedAt}`}
              innings={submitted.response.data.sample_match.innings}
              names={names}
            />
          )}
          <SampleScorecard key={`card-${submitted.completedAt}`} run={submitted} names={names} />
        </>
      ) : baseRequest ? (
        <div className="unrun-plan">
          <div className="panel-caption">
            <h2>Supplied scenario · ready to run</h2>
            <span>
              {baseRequest.team_a.team_id} / {baseRequest.team_b.team_id}
            </span>
          </div>
          <ServiceNote>
            Evidence before {formatDate(baseRequest.as_of)}. {baseRequest.batting_first_team_id}{' '}
            bats first. The simulation service will validate roster membership and playing
            constraints before running.
          </ServiceNote>
          <div className="unrun-plans">
            <SuppliedPlans request={baseRequest} names={names} />
          </div>
        </div>
      ) : null}
      <section className="scenario-transfer">
        <details>
          <summary>
            Load an explicit scenario request <span aria-hidden="true">+</span>
          </summary>
          <div className="scenario-transfer-body">
            <p>
              Import a simulation request for {ids[0]} and {ids[1]} at this ground. It must include
              both XIs, batting orders and 20-over bowling plans. The backend validates eligibility
              proxies and rules; this is a hypothetical planning exercise.
            </p>
            <div className="transfer-actions">
              <button
                className="text-button"
                disabled={busy || match?.season === 2025}
                onClick={() => fileRef.current?.click()}
              >
                Choose request file <span aria-hidden="true">↑</span>
              </button>
              <button
                className="text-button"
                onClick={() =>
                  saveJson(baseRequest || exampleRequest, 'concourse-request-template.json')
                }
              >
                {baseRequest ? 'Save current request' : 'Save CSK–MI example request'}{' '}
                <span aria-hidden="true">↓</span>
              </button>
              {example && (
                <button
                  className="text-button"
                  disabled={busy}
                  onClick={() => {
                    setBaseRequest(exampleRequest);
                    setTrials(exampleRequest.simulations);
                    setSeed(String(exampleRequest.seed));
                    setAssumeAvailability(exampleRequest.allow_unknown_availability);
                    simulation.restore(savedRun);
                    setImportError('');
                    setJson('');
                  }}
                >
                  Restore saved example
                </button>
              )}
            </div>
            <input
              ref={fileRef}
              type="file"
              accept=".json,application/json"
              className="sr-only"
              aria-label="Import scenario request JSON"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                e.target.value = '';
                if (!file) return;
                if (file.size > 65536) {
                  setImportError('Use a scenario request smaller than 64 KB.');
                  return;
                }
                try {
                  apply(await file.text());
                } catch {
                  setImportError('The request file could not be read.');
                }
              }}
            />
            <label className="scenario-json-label" htmlFor="scenario-json">
              Or paste request JSON
            </label>
            <textarea
              id="scenario-json"
              spellCheck={false}
              value={json}
              onChange={(e) => setJson(e.target.value)}
              placeholder={'{ "as_of": "2026-…", "team_a": { … }, "team_b": { … } }'}
              disabled={busy || match?.season === 2025}
            />
            <button
              className="text-button"
              disabled={busy || !json.trim() || match?.season === 2025}
              onClick={() => apply(json)}
            >
              Load request <Icon name="arrow" />
            </button>
            {importError && (
              <p role="alert" className="import-error">
                {importError}
              </p>
            )}
          </div>
        </details>
      </section>
      <footer className="page-footer">
        <span>The Concourse / Match planning</span>
        <span className="mono">Experimental model · 02</span>
      </footer>
      {factsOpen && match && (
        <MatchRecord
          match={match}
          missing={false}
          source={source}
          onClose={() => setFactsOpen(false)}
        />
      )}
    </main>
  );
}
