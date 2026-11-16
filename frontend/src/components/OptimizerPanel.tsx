import { useState } from 'react';
import {
  requestKey,
  type OptimizationRequest,
  type OptimizationRun,
  type OptimizedCandidate,
  type Roster,
} from '../api/lab';
import { availability, type OptimizerSettings } from '../domain/lab';
import { percent } from '../domain/simulation';
import { team } from '../domain/teams';
import { RangeBar } from './SimulationCharts';
import { Icon, RouteBullet, ServiceNote, SplitFlap, TagToggle } from './Signs';

function CandidateResult({
  run,
  selected,
  onSelect,
  apply,
  canApply,
  names,
}: {
  run: OptimizationRun;
  selected: number;
  onSelect: (index: number) => void;
  apply: (candidate: OptimizedCandidate) => void;
  canApply: boolean;
  names: Record<string, string>;
}) {
  const result = run.response.data,
    candidates = [result.recommended, ...result.alternatives],
    candidate = candidates[Math.min(selected, candidates.length - 1)],
    confirmation = result.confirmation.selected_team_outcome;
  return (
    <div className="optimizer-result">
      <div className="optimizer-source">
        <span className="eyebrow">
          {run.source === 'saved' ? 'Saved optimizer example' : 'Completed optimizer run'}
        </span>
        <span className="mono">{run.request.simulations} trials / candidate</span>
      </div>
      <div className="candidate-switch">
        {candidates.map((c, i) => (
          <TagToggle
            key={c.candidate_rank_by_proxy}
            active={selected === i}
            onClick={() => onSelect(i)}
          >
            {i === 0 ? 'Recommended' : `Alternative ${i}`}{' '}
            <span className="mono">{percent(c.simulation.probability)}</span>
          </TagToggle>
        ))}
      </div>
      <div className="candidate-verdict">
        <div>
          <span className="eyebrow">
            {selected === 0 ? 'Independent confirmation' : 'Candidate selection trials'}
          </span>
          <SplitFlap
            value={(
              (selected === 0 ? confirmation.probability : candidate.simulation.probability) * 100
            ).toFixed(1)}
            label={`${percent(selected === 0 ? confirmation.probability : candidate.simulation.probability)} simulated win share`}
          />
          <span className="candidate-unit">% simulated win share</span>
        </div>
        <div>
          <strong>
            {selected === 0 ? 'New trials. Same selected XI.' : 'An alternative candidate.'}
          </strong>
          <p>
            {selected === 0
              ? `Confirmation uses seed ${result.confirmation.seed}. This is a separate run, not historical validation.`
              : 'The independent confirmation applies only to the recommended candidate.'}
          </p>
        </div>
      </div>
      <div className="candidate-interval">
        <span>
          95% sampling interval{' '}
          <strong className="mono">
            {percent(
              (selected === 0 ? confirmation : candidate.simulation).sampling_interval.lower,
            )}
            —
            {percent(
              (selected === 0 ? confirmation : candidate.simulation).sampling_interval.upper,
            )}
          </strong>
        </span>
        <RangeBar
          lower={(selected === 0 ? confirmation : candidate.simulation).sampling_interval.lower}
          upper={(selected === 0 ? confirmation : candidate.simulation).sampling_interval.upper}
          value={(selected === 0 ? confirmation : candidate.simulation).probability}
        />
      </div>
      <div className="candidate-plan-summary">
        <RouteBullet id={run.request.team_id} small />
        <span>Proxy candidate #{candidate.candidate_rank_by_proxy}</span>
        <span className="mono">Selection trials {percent(candidate.simulation.probability)}</span>
      </div>
      <ol className="candidate-order">
        {candidate.plan.batting_order.map((id, i) => (
          <li key={id}>
            <span className="mono">{String(i + 1).padStart(2, '0')}</span>
            <strong>{names[id] || id}</strong>
          </li>
        ))}
      </ol>
      <button
        className="yellow-button apply-candidate"
        disabled={!canApply}
        onClick={() => apply(candidate)}
      >
        Apply this candidate to the active scenario <Icon name="arrow" />
      </button>
      <ServiceNote>
        {canApply
          ? 'Applying replaces this team’s XI, order, bowling plan and any substitute/Impact nomination. Run the scenario again to update its result.'
          : 'Inputs have changed. Run the optimizer again before applying a candidate.'}
      </ServiceNote>
      <details className="optimizer-method">
        <summary>Selection method and constraints</summary>
        <dl>
          <div>
            <dt>Selection basis</dt>
            <dd>
              {String(
                result.reliability.selection_basis || 'Noisy candidate comparison',
              ).replaceAll('_', ' ')}
            </dd>
          </div>
          <div>
            <dt>Global win optimum</dt>
            <dd>Not proven</dd>
          </div>
          <div>
            <dt>Surrogate optimum for this candidate</dt>
            <dd>
              {candidate.proxy_optimality_proven
                ? 'Proven by solver'
                : 'Not proven within solver budget'}
            </dd>
          </div>
          <div>
            <dt>Proxy utility</dt>
            <dd className="mono">{candidate.proxy_score.toFixed(3)} · not expected runs</dd>
          </div>
          <div>
            <dt>Batting order / captain</dt>
            <dd>Heuristic order; first batter is a placeholder captain</dd>
          </div>
        </dl>
        <p>
          Eleven players, up to four overseas proxies, a keeper, batting-role balance, at most four
          overs per bowler and no consecutive overs. Bowler/all-rounder roles restrict the
          optimizer's bowling pool.
        </p>
        <p>Impact replacements are not optimized. Match eligibility remains unverified.</p>
      </details>
      {result.exclusions.length > 0 && (
        <details className="optimizer-method">
          <summary>{result.exclusions.length} candidates excluded by service</summary>
          <ul>
            {result.exclusions.map((e) => (
              <li key={e.player_id}>
                {names[e.player_id] || e.player_id}: {e.reason.replaceAll('_', ' ')}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export default function OptimizerPanel({
  request,
  settings,
  roster,
  names,
  issues,
  run,
  busy,
  onSettings,
  onRun,
  onApply,
}: {
  request: OptimizationRequest;
  settings: OptimizerSettings;
  roster: Roster;
  names: Record<string, string>;
  issues: string[];
  run: OptimizationRun | null;
  busy: boolean;
  onSettings: (settings: OptimizerSettings) => void;
  onRun: () => void;
  onApply: (candidate: OptimizedCandidate) => void;
}) {
  const [query, setQuery] = useState(''),
    [selected, setSelected] = useState(0),
    fresh = Boolean(run && requestKey(request) === requestKey(run.request));
  function mark(id: string, type: 'locked' | 'excluded') {
    const list = settings[type].includes(id)
      ? settings[type].filter((p) => p !== id)
      : [...settings[type], id];
    onSettings({
      ...settings,
      [type]: list,
      [type === 'locked' ? 'excluded' : 'locked']: settings[
        type === 'locked' ? 'excluded' : 'locked'
      ].filter((p) => p !== id),
    });
  }
  return (
    <section className="optimizer-panel" aria-labelledby="optimizer-heading">
      <div className="lab-panel-heading">
        <div>
          <span className="eyebrow">03 / XI optimization</span>
          <h2 id="optimizer-heading">Build a candidate.</h2>
        </div>
        <RouteBullet id={request.team_id} />
      </div>
      <div className="optimizer-settings">
        <div>
          <span className="eyebrow">Team to select</span>
          <div className="filter-group">
            {(['team_a', 'team_b'] as const).map((side) => (
              <TagToggle
                key={side}
                active={settings.side === side}
                disabled={busy}
                onClick={() => {
                  setSelected(0);
                  onSettings({ ...settings, side, locked: [], excluded: [] });
                }}
              >
                {side === 'team_a' ? 'Team A' : 'Team B'}
              </TagToggle>
            ))}
          </div>
        </div>
        <div>
          <span className="eyebrow">Candidates</span>
          <div className="filter-group">
            {[1, 2, 3].map((n) => (
              <TagToggle
                key={n}
                active={settings.candidates === n}
                disabled={busy}
                onClick={() => onSettings({ ...settings, candidates: n })}
              >
                {n}
              </TagToggle>
            ))}
          </div>
        </div>
        <div>
          <span className="eyebrow">Trials per candidate</span>
          <div className="filter-group">
            {[50, 200, 500].map((n) => (
              <TagToggle
                key={n}
                active={settings.trials === n}
                disabled={busy}
                onClick={() => onSettings({ ...settings, trials: n })}
              >
                {n}
              </TagToggle>
            ))}
          </div>
        </div>
        <label>
          <span className="eyebrow">
            Risk aversion <strong className="mono">{settings.risk.toFixed(1)}</strong>
          </span>
          <input
            type="range"
            min="0"
            max="3"
            step="0.5"
            value={settings.risk}
            disabled={busy}
            onChange={(e) => onSettings({ ...settings, risk: Number(e.target.value) })}
          />
          <span className="optimizer-helper">0 = none · 3 = strongest proxy penalty</span>
        </label>
        <label>
          <span className="eyebrow">
            Minimum batting options <strong className="mono">{settings.minimumBatting}</strong>
          </span>
          <input
            type="range"
            min="0"
            max="11"
            step="1"
            value={settings.minimumBatting}
            disabled={busy}
            onChange={(e) => onSettings({ ...settings, minimumBatting: Number(e.target.value) })}
          />
          <span className="optimizer-helper">Batter, keeper/batter and all-rounder roles</span>
        </label>
      </div>
      <details className="candidate-pool">
        <summary>
          Candidate pool{' '}
          <span className="mono">
            {settings.locked.length} locked · {settings.excluded.length} excluded
          </span>
        </summary>
        <button
          className="text-button clear-candidate-filters"
          disabled={busy || (!settings.locked.length && !settings.excluded.length)}
          onClick={() => onSettings({ ...settings, locked: [], excluded: [] })}
        >
          Clear locks and exclusions ×
        </button>
        <label>
          <span className="sr-only">Search optimizer candidates</span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Find a candidate…"
          />
        </label>
        <div className="pool-rows">
          {roster.members
            .filter((m) => m.player.display_name.toLowerCase().includes(query.toLowerCase()))
            .map((m) => (
              <div key={m.player.player_id}>
                <span>
                  <strong>{m.player.display_name}</strong>
                  <small>
                    {(m.player.primary_role || 'Role unknown').replaceAll('_', ' ')} ·{' '}
                    {availability(m, request.as_of)}
                  </small>
                </span>
                <button
                  disabled={busy}
                  aria-pressed={settings.locked.includes(m.player.player_id)}
                  onClick={() => mark(m.player.player_id, 'locked')}
                  aria-label={`Lock ${m.player.display_name}`}
                >
                  Lock
                </button>
                <button
                  disabled={busy}
                  aria-pressed={settings.excluded.includes(m.player.player_id)}
                  onClick={() => mark(m.player.player_id, 'excluded')}
                  aria-label={`Exclude ${m.player.display_name}`}
                >
                  Exclude
                </button>
              </div>
            ))}
        </div>
      </details>
      <div className="optimizer-submit">
        <button
          className="yellow-button"
          disabled={busy || issues.length > 0}
          onClick={() => {
            setSelected(0);
            onRun();
          }}
        >
          Optimize {team(request.team_id).short} XI <Icon name="arrow" />
        </button>
        <p>
          Opponent plan is fixed. Up to three surrogate candidates are compared by simulation, then
          the selected XI receives an independent confirmation run.
        </p>
        {issues.length > 0 && (
          <ul className="optimizer-issues">
            {issues.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        )}
      </div>
      {run ? (
        <CandidateResult
          key={`${run.completedAt}-${requestKey(run.request)}`}
          run={run}
          selected={selected}
          onSelect={setSelected}
          names={names}
          canApply={fresh && !busy}
          apply={onApply}
        />
      ) : (
        <ServiceNote>
          No optimizer result yet. The service will enforce the planning constraints before
          returning a candidate.
        </ServiceNote>
      )}
    </section>
  );
}
