import { useEffect, useRef, useState } from 'react';
import {
  exampleRequest,
  outcome,
  parseSimulationRequest,
  runSimulation,
  savedRun,
  type SimulationRequest,
  type TeamPlan,
} from '../api/simulation';
import {
  grounds,
  labData,
  optimizeXI,
  requestKey,
  savedOptimization,
  savedRosters,
  type OptimizedCandidate,
} from '../api/lab';
import {
  clone,
  comparisonReady,
  initialOptimizer,
  planIssues,
  optimizationRequest,
  optimizerIssues,
  scenarioIssues,
  setToss,
  type LabSlot,
  type SlotId,
} from '../domain/lab';
import { formatDate } from '../domain/archive';
import { percent, sameRequest } from '../domain/simulation';
import { team, teams } from '../domain/teams';
import { usePlanning } from '../PlanningContext';
import { useLabRosters } from '../useLabRosters';
import { usePlanningJob } from '../usePlanningJob';
import PlanEditor from './PlanEditor';
import OptimizerPanel from './OptimizerPanel';
import { Icon, RouteBullet, ServiceNote, SplitFlap, TagToggle } from './Signs';
import '../lab.css';

const initialNames = Object.fromEntries(
  Object.values(savedRosters).flatMap((r) =>
    r.members.map((m) => [m.player.player_id, m.player.display_name]),
  ),
);
function initialSlot(): LabSlot {
  return {
    request: clone(exampleRequest),
    run: savedRun,
    toss: { winnerId: exampleRequest.batting_first_team_id, decision: 'bat' },
    names: initialNames,
    venueName: grounds.find((v) => v.venue_id === exampleRequest.venue_id)!.display_name,
  };
}
function emptyPlan(id: string): TeamPlan {
  return {
    team_id: id,
    starting_xi: [],
    batting_order: [],
    bowling_plan: Array(20).fill(''),
    captain_id: '',
    substitutes: [],
    impact: null,
  };
}

function ScenarioComparison({ a, b }: { a: LabSlot; b: LabSlot }) {
  const ready = comparisonReady(a, b),
    id = a.request.team_a.team_id;
  const first = ready ? outcome(a.run!.response.data, id).probability : 0,
    second = ready ? outcome(b.run!.response.data, id).probability : 0,
    delta = (second - first) * 100;
  return (
    <section className="scenario-comparison">
      <div className="lab-panel-heading">
        <div>
          <span className="eyebrow">04 / Scenario comparison</span>
          <h2>A → B</h2>
        </div>
        <span className="mono">Matched run settings</span>
      </div>
      {ready ? (
        <>
          <div className="comparison-values">
            <div>
              <span className="eyebrow">A / {id} simulated wins</span>
              <strong className="mono">{percent(first)}</strong>
              <small>
                {a.run!.request.simulations} trials · seed {a.run!.request.seed}
              </small>
            </div>
            <div>
              <span className="eyebrow">B / {id} simulated wins</span>
              <strong className="mono">{percent(second)}</strong>
              <small>
                {b.run!.request.simulations} trials · seed {b.run!.request.seed}
              </small>
            </div>
            <div className="comparison-delta">
              <span className="eyebrow">B minus A</span>
              <strong className="mono">
                {delta > 0 ? '+' : ''}
                {delta.toFixed(1)}
                <small>pp</small>
              </strong>
              <span>percentage points</span>
            </div>
          </div>
          <div className="scenario-differences">
            <span className="eyebrow">Inputs changed</span>
            <ul>
              {(
                [
                  'as_of',
                  'venue_id',
                  'batting_first_team_id',
                  'team_a',
                  'team_b',
                  'simulations',
                  'seed',
                  'sample_posterior',
                  'use_delivery_calibration',
                  'allow_unknown_availability',
                  'max_super_overs',
                ] as const
              )
                .filter((k) => requestKey(a.request[k]) !== requestKey(b.request[k]))
                .map((k) => (
                  <li key={k}>
                    {
                      {
                        venue_id: 'Ground',
                        batting_first_team_id: 'Batting first',
                        team_a: 'Team A plan',
                        team_b: 'Team B plan',
                        as_of: 'Evidence cutoff',
                        simulations: 'Trial count',
                        seed: 'Seed',
                        sample_posterior: 'Posterior sampling',
                        use_delivery_calibration: 'Delivery correction',
                        allow_unknown_availability: 'Availability assumption',
                        max_super_overs: 'Super Over cap',
                      }[k]
                    }
                  </li>
                ))}
            </ul>
          </div>
          <ServiceNote>
            This is a descriptive change between finite simulation runs, not a significance test, a
            guaranteed benefit or historical validation.
          </ServiceNote>
        </>
      ) : (
        <div className="comparison-empty">
          <span className="comparison-placeholder mono">— pp</span>
          <p>
            Run both current scenarios with the same teams, evidence cutoff, trial count and seed.
            Model and dataset versions must match. Editing a draft makes its earlier result
            ineligible for comparison.
          </p>
        </div>
      )}
    </section>
  );
}

export default function LabWorkspace({
  theme,
  onTheme,
  onMatch,
}: {
  theme: string;
  onTheme: () => void;
  onMatch: (slot: SlotId) => void;
}) {
  const store = usePlanning(),
    { active, setActive, side, setSide, setSettings, setOptimization } = store,
    settings = store.settings || initialOptimizer,
    optimization = store.optimization || savedOptimization,
    [teamPicker, setTeamPicker] = useState(false),
    [groundPicker, setGroundPicker] = useState(false),
    [groundQuery, setGroundQuery] = useState('');
  const slot = store.slots?.[active],
    request = slot?.request || exampleRequest;
  const { rosters, sources, checking, retry } = useLabRosters(
      request.team_a.team_id,
      request.team_b.team_id,
    ),
    job = usePlanningJob(),
    heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (!store.slots) {
      const a = initialSlot();
      store.initialize({ A: a, B: { ...clone(a), run: null } });
    }
    heading.current?.focus();
  }, []);
  const names = {
    ...initialNames,
    ...Object.fromEntries(
      Object.values(rosters).flatMap((r) =>
        r.members.map((m) => [m.player.player_id, m.player.display_name]),
      ),
    ),
  };
  if (!store.slots || !slot)
    return (
      <main className="concourse">
        <div className="empty-state" role="status">
          <h2>Preparing Lab</h2>
        </div>
      </main>
    );
  const issues = scenarioIssues(request, rosters),
    selectedPlan = request[side],
    opponent = request[side === 'team_a' ? 'team_b' : 'team_a'];
  const optRequest = optimizationRequest(request, settings),
    optIssues = optimizerIssues(optRequest, rosters);
  const latest = slot.run,
    fresh = Boolean(latest && sameRequest(latest.request, request));
  function edit(next: SimulationRequest, toss = slot!.toss) {
    if (!job.busy)
      store.edit(
        active,
        next,
        toss,
        grounds.find((v) => v.venue_id === next.venue_id)?.display_name || next.venue_id,
      );
  }
  function planChange(plan: TeamPlan) {
    edit({ ...request, [side]: plan });
  }
  function changeTeam(id: string) {
    if (id === opponent.team_id || job.busy) return;
    const next = { ...request, [side]: emptyPlan(id) };
    const first =
      request.batting_first_team_id === selectedPlan.team_id ? id : request.batting_first_team_id;
    const toss = {
      ...slot!.toss,
      winnerId: slot!.toss.winnerId === selectedPlan.team_id ? id : slot!.toss.winnerId,
    };
    edit({ ...next, batting_first_team_id: first }, toss);
    setSettings({ ...initialOptimizer, side: settings.side });
    setTeamPicker(false);
  }
  function simulate() {
    if (issues.length || job.busy) return;
    const submitted = parseSimulationRequest(clone(request)),
      target = active;
    job.start(
      'Match simulation',
      (signal) => runSimulation(submitted, signal),
      (response) =>
        store.complete(target, {
          request: submitted,
          response,
          source: 'api',
          completedAt: new Date().toISOString(),
        }),
      45000,
    );
  }
  function optimize() {
    if (optIssues.length || job.busy) return;
    const submitted = clone(optRequest);
    job.start(
      'XI optimization',
      (signal) => optimizeXI(submitted, signal),
      (response) => {
        const returned = [response.data.recommended, ...response.data.alternatives];
        const invalid = returned.flatMap((candidate) =>
          planIssues(
            candidate.plan,
            rosters[submitted.team_id],
            submitted.team_id === submitted.batting_first_team_id,
            submitted.as_of,
            submitted.allow_unknown_availability,
          ),
        );
        if (invalid.length)
          throw new Error(`Returned candidate failed local planning checks: ${invalid[0]}`);
        setOptimization({
          request: submitted,
          response,
          source: 'api',
          completedAt: new Date().toISOString(),
        });
      },
    );
  }
  function apply(candidate: OptimizedCandidate) {
    if (!optimization || requestKey(optimization.request) !== requestKey(optRequest) || job.busy)
      return;
    edit({ ...request, [settings.side]: clone(candidate.plan) });
    setSide(settings.side);
  }
  function exportRequest() {
    try {
      const normalized = parseSimulationRequest(request),
        url = URL.createObjectURL(
          new Blob([JSON.stringify(normalized, null, 2)], { type: 'application/json' }),
        ),
        link = document.createElement('a');
      link.href = url;
      link.download = `concourse-scenario-${active}.json`;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      /* Validation is displayed in the plan panels. */
    }
  }
  return (
    <main className="concourse lab-workspace" id="lab-content" tabIndex={-1}>
      <header className="lab-header">
        <div>
          <span className="eyebrow">The Concourse / 03 / Planning</span>
          <h1 ref={heading} tabIndex={-1}>
            Lab<span aria-hidden="true">↗</span>
          </h1>
          <p>Two scenarios. Explicit team plans.</p>
        </div>
        <div className="lab-header-key">
          <Icon name="toss" />
          <span className="eyebrow">2026 planning profile</span>
          <strong>
            Change the inputs.
            <br />
            Then run the match.
          </strong>
          <span>Experimental · eligibility unverified</span>
        </div>
        <button
          className="lab-theme icon-button"
          onClick={onTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        >
          <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
        </button>
      </header>
      <div className="scenario-slots" aria-label="Scenario slots">
        {(['A', 'B'] as const).map((id) => {
          const s = store.slots![id],
            current = s.run && sameRequest(s.run.request, s.request);
          return (
            <button
              key={id}
              className={`scenario-slot ${active === id ? 'selected' : ''}`}
              aria-pressed={active === id}
              disabled={job.busy}
              onClick={() => {
                setActive(id);
                setSettings({ ...initialOptimizer });
                setTeamPicker(false);
              }}
            >
              <span className="slot-letter">{id}</span>
              <span>
                <strong>
                  {s.request.team_a.team_id} v {s.request.team_b.team_id}
                </strong>
                <small>
                  {current
                    ? `${s.run!.source === 'saved' ? 'Saved' : 'API'} result · ${s.run!.request.simulations} trials`
                    : s.run
                      ? 'Draft changed · previous result retained'
                      : 'Draft · not run'}
                </small>
              </span>
              <span className="slot-state mono">
                {current
                  ? percent(outcome(s.run!.response.data, s.request.team_a.team_id).probability)
                  : '—'}
              </span>
            </button>
          );
        })}
        <button
          className="copy-scenario"
          disabled={job.busy}
          onClick={() => {
            const to = active === 'A' ? 'B' : 'A';
            store.copy(active, to);
            setActive(to);
            setSettings(initialOptimizer);
          }}
        >
          Copy {active} to {active === 'A' ? 'B' : 'A'} <span aria-hidden="true">→</span>
        </button>
      </div>
      <section className="lab-conditions" aria-label="Scenario setup">
        <div className="condition-block">
          <span className="eyebrow">01 / Scenario toss</span>
          <div className="filter-group">
            {[request.team_a.team_id, request.team_b.team_id].map((id) => (
              <TagToggle
                key={id}
                active={slot.toss.winnerId === id}
                disabled={job.busy}
                onClick={() => {
                  const toss = { ...slot.toss, winnerId: id };
                  edit(setToss(request, toss), toss);
                }}
              >
                {id} wins toss
              </TagToggle>
            ))}
          </div>
          <div className="filter-group">
            {(['bat', 'field'] as const).map((decision) => (
              <TagToggle
                key={decision}
                active={slot.toss.decision === decision}
                disabled={job.busy}
                onClick={() => {
                  const toss = { ...slot.toss, decision };
                  edit(setToss(request, toss), toss);
                }}
              >
                {decision === 'bat' ? 'Bat' : 'Field'}
              </TagToggle>
            ))}
          </div>
          <p>
            <strong>{request.batting_first_team_id} bats first.</strong> Only batting-first order is
            passed to the model.
          </p>
        </div>
        <div className="condition-block">
          <span className="eyebrow">Ground</span>
          <button
            className="ground-select"
            disabled={job.busy}
            aria-expanded={groundPicker}
            onClick={() => setGroundPicker((v) => !v)}
          >
            {grounds.find((v) => v.venue_id === request.venue_id)?.display_name || request.venue_id}
            <span>+</span>
          </button>
          <label className="cutoff-field">
            <span className="eyebrow">Evidence before · exclusive</span>
            <input
              type="date"
              min="2008-04-19"
              max="2099-12-31"
              value={request.as_of}
              disabled={job.busy}
              onChange={(e) => edit({ ...request, as_of: e.target.value })}
            />
          </label>
        </div>
        <div className="condition-block lab-run-settings">
          <span className="eyebrow">Simulation trials</span>
          <div className="filter-group">
            {[50, 200, 500, 1000].map((n) => (
              <TagToggle
                key={n}
                active={request.simulations === n}
                disabled={job.busy}
                onClick={() => edit({ ...request, simulations: n })}
              >
                {n.toLocaleString()}
              </TagToggle>
            ))}
          </div>
          <label className="lab-seed">
            <span className="eyebrow">Seed</span>
            <input
              type="number"
              min="0"
              max="4294967295"
              step="1"
              value={Number.isFinite(request.seed) ? request.seed : ''}
              disabled={job.busy}
              onChange={(e) =>
                edit({ ...request, seed: e.target.value === '' ? NaN : Number(e.target.value) })
              }
            />
          </label>
        </div>
      </section>
      {groundPicker && (
        <div className="lab-ground-picker">
          <input
            aria-label="Search grounds"
            value={groundQuery}
            onChange={(e) => setGroundQuery(e.target.value)}
            placeholder="Find a ground or city…"
          />
          <div>
            {grounds
              .filter((v) =>
                `${v.display_name} ${v.city}`.toLowerCase().includes(groundQuery.toLowerCase()),
              )
              .map((v) => (
                <TagToggle
                  key={v.venue_id}
                  active={request.venue_id === v.venue_id}
                  disabled={job.busy}
                  onClick={() => {
                    edit({ ...request, venue_id: v.venue_id });
                    setGroundPicker(false);
                  }}
                >
                  {v.display_name}
                </TagToggle>
              ))}
          </div>
        </div>
      )}
      <div className="lab-policy-row">
        <label>
          <input
            type="checkbox"
            checked={request.allow_unknown_availability}
            disabled={job.busy}
            onChange={(e) => edit({ ...request, allow_unknown_availability: e.target.checked })}
          />
          Assume unknown player availability for planning
        </label>
        <button disabled={checking || job.busy} onClick={retry}>
          {checking ? 'Checking rosters…' : 'Refresh roster connection'} ↗
        </button>
        <span>Saved dataset {labData.dataset_version}</span>
      </div>
      <div
        className={`lab-job-status ${job.state.phase === 'failed' ? 'error' : ''}`}
        role="status"
        aria-live="polite"
      >
        <span className="status-square" />
        <div>
          <strong>
            {job.state.phase === 'running'
              ? `${job.state.label} in progress`
              : job.state.phase === 'failed'
                ? 'Planning request failed'
                : job.state.phase === 'complete'
                  ? `${job.state.label} complete`
                  : job.state.phase === 'cancelled'
                    ? 'Stopped waiting'
                    : fresh
                      ? `Scenario ${active} result ready`
                      : `Scenario ${active} draft`}
          </strong>
          <p>
            {job.state.phase === 'failed'
              ? job.state.message
              : job.state.phase === 'cancelled'
                ? 'The backend may finish the submitted job. Late replies will not replace these results.'
                : job.busy
                  ? 'The service returns a complete result. Previous outputs remain labelled below.'
                  : fresh
                    ? `${latest!.source === 'saved' ? 'Saved project output' : 'Local API output'} · evidence before ${formatDate(latest!.request.as_of)}`
                    : 'Run the current draft to update estimates. Earlier output does not change as you edit.'}
          </p>
        </div>
        {job.busy && (
          <button className="text-button" onClick={job.cancel}>
            Stop waiting ×
          </button>
        )}
      </div>
      <div className="lab-main">
        <div className="lab-editor-column">
          <div className="editing-team">
            <div className="filter-group">
              {(['team_a', 'team_b'] as const).map((s) => (
                <TagToggle
                  key={s}
                  active={side === s}
                  onClick={() => {
                    setSide(s);
                    setTeamPicker(false);
                  }}
                >
                  <RouteBullet id={request[s].team_id} small />
                  {s === 'team_a' ? 'Team A' : 'Team B'} / {request[s].team_id}
                </TagToggle>
              ))}
            </div>
            <button
              className="text-button"
              disabled={job.busy}
              onClick={() => setTeamPicker((v) => !v)}
            >
              Change team {teamPicker ? '−' : '+'}
            </button>
          </div>
          {teamPicker && (
            <div className="team-picker">
              {Object.keys(teams).map((id) => (
                <TagToggle
                  key={id}
                  active={selectedPlan.team_id === id}
                  disabled={job.busy || opponent.team_id === id}
                  onClick={() => changeTeam(id)}
                >
                  <RouteBullet id={id} small />
                  {team(id).short}
                </TagToggle>
              ))}
            </div>
          )}
          <PlanEditor
            key={`${side}-${selectedPlan.team_id}`}
            plan={selectedPlan}
            roster={rosters[selectedPlan.team_id]}
            source={sources[selectedPlan.team_id] || 'saved'}
            asOf={request.as_of}
            battingFirst={selectedPlan.team_id === request.batting_first_team_id}
            allowUnknown={request.allow_unknown_availability}
            disabled={job.busy}
            onChange={planChange}
          />
        </div>
        <aside className="lab-result-column">
          <section className="scenario-result">
            <div className="lab-panel-heading">
              <div>
                <span className="eyebrow">Scenario {active}</span>
                <h2>Run the plan.</h2>
              </div>
              <span className="mono">
                {fresh ? 'Current result' : latest ? 'Previous result' : 'Not run'}
              </span>
            </div>
            {latest ? (
              <>
                <div className={`lab-odds ${fresh ? '' : 'stale'}`}>
                  <RouteBullet id={latest.request.team_a.team_id} />
                  <div>
                    <SplitFlap
                      value={(
                        outcome(latest.response.data, latest.request.team_a.team_id).probability *
                        100
                      ).toFixed(1)}
                      label={`${latest.request.team_a.team_id} win share ${percent(outcome(latest.response.data, latest.request.team_a.team_id).probability)}`}
                    />
                    <span>% simulated win share</span>
                  </div>
                </div>
                <p className="lab-result-caption">
                  {latest.source === 'saved' ? 'Saved output' : 'API output'} ·{' '}
                  {latest.request.simulations} trials · seed {latest.request.seed}
                  {!fresh ? ' · Inputs changed' : ''}
                </p>
              </>
            ) : (
              <p className="no-scenario-result">No result for this slot.</p>
            )}
            <div className="scenario-actions">
              <button
                className="yellow-button"
                disabled={job.busy || issues.length > 0}
                onClick={simulate}
              >
                Run scenario {active} <Icon name="arrow" />
              </button>
              <button
                className="text-button"
                disabled={job.busy || issues.length > 0}
                onClick={() => onMatch(active)}
              >
                Open in Match <Icon name="arrow" />
              </button>
              <button className="text-button" disabled={issues.length > 0} onClick={exportRequest}>
                Save request ↓
              </button>
            </div>
            {issues.length > 0 && (
              <details className="scenario-issues" open>
                <summary>{issues.length} scenario checks</summary>
                <ul>
                  {issues.map((i) => (
                    <li key={i}>{i}</li>
                  ))}
                </ul>
              </details>
            )}
            <ServiceNote>
              Win estimates are experimental. The displayed interval in Match measures sampling
              error, not predictive accuracy.
            </ServiceNote>
          </section>
          <ScenarioComparison a={store.slots.A} b={store.slots.B} />
          <section className="lab-scope-note">
            <Icon name="pitch" />
            <h2>Model the supported inputs.</h2>
            <p>
              Venue, historical player/phase evidence and explicit plans inform the run. Score
              pressure, measured pitch, dew, weather and live injury effects are not learned by this
              model.
            </p>
            <p>
              Role, overseas and keeper labels are current profile proxies. Match eligibility
              remains unverified.
            </p>
          </section>
        </aside>
      </div>
      <OptimizerPanel
        request={optRequest}
        settings={settings}
        roster={rosters[optRequest.team_id]}
        names={names}
        issues={optIssues}
        run={optimization}
        busy={job.busy}
        onSettings={setSettings}
        onRun={optimize}
        onApply={apply}
      />
      <footer className="page-footer">
        <span>The Concourse / Lab</span>
        <span className="mono">Planning edition · 03</span>
      </footer>
    </main>
  );
}
