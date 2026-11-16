import { useState } from 'react';
import type { TeamPlan } from '../api/simulation';
import type { Roster } from '../api/lab';
import {
  activePlayers,
  availability,
  moveBatter,
  planIssues,
  reconcilePlan,
  toggleStarter,
} from '../domain/lab';
import { team } from '../domain/teams';
import { RouteBullet, ServiceNote, TagToggle } from './Signs';

const roleNames: Record<string, string> = {
  batter: 'Batter',
  bowler: 'Bowler',
  allrounder: 'All-rounder',
  wicketkeeper_batter: 'Keeper / batter',
};
export default function PlanEditor({
  plan,
  roster,
  source,
  asOf,
  battingFirst,
  allowUnknown,
  disabled,
  onChange,
}: {
  plan: TeamPlan;
  roster: Roster;
  source: string;
  asOf: string;
  battingFirst: boolean;
  allowUnknown: boolean;
  disabled: boolean;
  onChange: (plan: TeamPlan) => void;
}) {
  const [tab, setTab] = useState<'xi' | 'overs' | 'impact'>('xi'),
    [query, setQuery] = useState(''),
    [over, setOver] = useState(0),
    [impactOut, setImpactOut] = useState(plan.impact?.outgoing_id || '');
  const outgoing = plan.impact?.outgoing_id || impactOut;
  const names = Object.fromEntries(
    roster.members.map((m) => [m.player.player_id, m.player.display_name]),
  );
  const active = activePlayers(plan, battingFirst),
    issues = planIssues(plan, roster, battingFirst, asOf, allowUnknown);
  const overseas = plan.starting_xi.filter(
    (id) => roster.members.find((m) => m.player.player_id === id)?.player.is_overseas,
  ).length;
  const keeper = active.bowling.filter(
    (id) => roster.members.find((m) => m.player.player_id === id)?.player.is_wicketkeeper,
  ).length;
  const filtered = roster.members.filter((m) =>
    `${m.player.display_name} ${roleNames[m.player.primary_role || ''] || ''} ${m.player.country}`
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  function update(p: TeamPlan) {
    onChange(reconcilePlan(p, battingFirst));
  }
  return (
    <section className="lab-plan" aria-labelledby="plan-heading">
      <div className="lab-panel-heading">
        <div>
          <span className="eyebrow">02 / Team plan</span>
          <h2 id="plan-heading">
            <RouteBullet id={plan.team_id} />
            {team(plan.team_id).name}
          </h2>
        </div>
        <span className="mono">
          {source === 'api' ? 'Local API roster' : 'Saved roster snapshot'}
        </span>
      </div>
      <div className="plan-gauges">
        <span>
          XI <strong className="mono">{plan.starting_xi.length}/11</strong>
        </span>
        <span>
          Overseas proxy <strong className="mono">{overseas}/4</strong>
        </span>
        <span>
          Fielding keepers <strong className="mono">{keeper}</strong>
        </span>
      </div>
      <div className="lab-tabs">
        <TagToggle active={tab === 'xi'} onClick={() => setTab('xi')}>
          Batting order
        </TagToggle>
        <TagToggle active={tab === 'overs'} onClick={() => setTab('overs')}>
          20 overs
        </TagToggle>
        <TagToggle active={tab === 'impact'} onClick={() => setTab('impact')}>
          Interval Impact
        </TagToggle>
      </div>
      {tab === 'xi' && (
        <div className="lineup-workbench">
          <div className="batting-strips">
            <div className="strip-caption">
              <span>Drag to reorder · arrows also work</span>
              <span className="mono">{battingFirst ? 'Batting first' : 'Chasing'}</span>
            </div>
            <ol>
              {plan.batting_order.map((id, index) => (
                <li
                  key={id}
                  draggable={!disabled}
                  onDragStart={(e) => {
                    e.dataTransfer.setData('text/plain', String(index));
                    e.dataTransfer.effectAllowed = 'move';
                  }}
                  onDragOver={(e) => {
                    if (!disabled) e.preventDefault();
                  }}
                  onDrop={(e) => {
                    e.preventDefault();
                    const raw = e.dataTransfer.getData('text/plain'),
                      from = Number(raw);
                    if (!disabled && /^\d+$/.test(raw) && Number.isInteger(from))
                      onChange(moveBatter(plan, from, index));
                  }}
                >
                  <span className="drag-grip" aria-hidden="true" />
                  <span className="strip-position mono">{String(index + 1).padStart(2, '0')}</span>
                  <strong>{names[id] || id}</strong>
                  <button
                    className={`captain-button ${plan.captain_id === id ? 'chosen' : ''}`}
                    disabled={disabled || !plan.starting_xi.includes(id)}
                    onClick={() => onChange({ ...plan, captain_id: id })}
                    aria-pressed={plan.captain_id === id}
                    aria-label={`Make ${names[id] || id} captain`}
                    title="Captain is a required label, not a predictive input"
                  >
                    C
                  </button>
                  <div className="strip-arrows">
                    <button
                      aria-label={`Move ${names[id] || id} up`}
                      disabled={disabled || index === 0}
                      onClick={() => onChange(moveBatter(plan, index, index - 1))}
                    >
                      ↑
                    </button>
                    <button
                      aria-label={`Move ${names[id] || id} down`}
                      disabled={disabled || index === plan.batting_order.length - 1}
                      onClick={() => onChange(moveBatter(plan, index, index + 1))}
                    >
                      ↓
                    </button>
                  </div>
                  <button
                    className="remove-player"
                    aria-label={`Remove ${names[id] || id} from the plan`}
                    disabled={disabled}
                    onClick={() => {
                      if (plan.starting_xi.includes(id))
                        onChange(toggleStarter(plan, id, battingFirst));
                      else update({ ...plan, impact: null });
                    }}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ol>
            {plan.starting_xi.length < 11 && (
              <div className="empty-xi-slots">
                <strong className="mono">{11 - plan.starting_xi.length}</strong>
                <span>
                  starting {11 - plan.starting_xi.length === 1 ? 'place' : 'places'} to fill from
                  the roster
                </span>
              </div>
            )}
            <ServiceNote>
              {plan.impact && !battingFirst
                ? 'Batting XI includes the nominated interval replacement. '
                : ''}
              Captaincy is a required plan label; the model does not estimate leadership.
            </ServiceNote>
          </div>
          <div className="roster-board">
            <label className="roster-search">
              <span className="eyebrow">Roster / {roster.members.length}</span>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Find a player or role…"
                aria-label="Search team roster"
              />
            </label>
            <div className="roster-list">
              {filtered.map(({ player: p, availability: status }) => {
                const selected = plan.starting_xi.includes(p.player_id),
                  effective = availability({ player: p, availability: status }, asOf);
                return (
                  <div className={`roster-player ${selected ? 'selected' : ''}`} key={p.player_id}>
                    <div>
                      <strong>{p.display_name}</strong>
                      <span>
                        {roleNames[p.primary_role || ''] || 'Role unknown'} ·{' '}
                        {p.is_overseas === null
                          ? 'Classification unknown'
                          : p.is_overseas
                            ? 'Overseas proxy'
                            : 'Domestic proxy'}
                      </span>
                      <small>
                        {effective === 'unknown'
                          ? 'Availability unknown'
                          : effective === 'unavailable'
                            ? 'Dated unavailable'
                            : 'Dated available'}
                      </small>
                    </div>
                    <button
                      disabled={disabled || (!selected && plan.starting_xi.length === 11)}
                      aria-pressed={selected}
                      aria-label={`${selected ? 'Remove' : 'Select'} ${p.display_name} ${selected ? 'from' : 'for'} starting XI`}
                      onClick={() => onChange(toggleStarter(plan, p.player_id, battingFirst))}
                    >
                      {selected ? 'XI' : '+'}
                    </button>
                  </div>
                );
              })}
              {!filtered.length && <p className="roster-empty">No players match this filter.</p>}
            </div>
            <p className="roster-proxy-note">
              Role, keeper and overseas labels are saved profile proxies. Select eleven starters;
              remove a player before adding a replacement.
            </p>
          </div>
        </div>
      )}
      {tab === 'overs' && (
        <div className="bowling-workbench">
          <p>
            Select an over, then assign an active fielder. A bowler has a four-over limit and cannot
            bowl consecutive overs.
          </p>
          <div className="bowling-stations" aria-label="Bowling assignments">
            {plan.bowling_plan.map((id, index) => (
              <button
                key={index}
                className={`${index === over ? 'selected' : ''} ${!id ? 'unassigned' : ''}`}
                aria-pressed={index === over}
                aria-label={`Assign over ${index + 1}, ${names[id] || 'unassigned'}`}
                onClick={() => setOver(index)}
              >
                <span className="mono">{String(index + 1).padStart(2, '0')}</span>
                <strong>{id ? names[id]?.split(' ').at(-1) || id : '—'}</strong>
                <span>{index < 6 ? 'PP' : index < 16 ? 'MID' : 'DEATH'}</span>
              </button>
            ))}
          </div>
          <div className="over-assignment-title">
            <span className="eyebrow">Assign over {over + 1}</span>
            <span className="mono">{names[plan.bowling_plan[over]] || 'Unassigned'}</span>
          </div>
          <div className="bowler-options">
            {active.bowling.map((id) => {
              const count = plan.bowling_plan.filter((p) => p === id).length,
                quota = count - Number(plan.bowling_plan[over] === id) >= 4,
                adjacent = plan.bowling_plan[over - 1] === id || plan.bowling_plan[over + 1] === id;
              return (
                <button
                  key={id}
                  disabled={disabled || quota || adjacent}
                  aria-pressed={plan.bowling_plan[over] === id}
                  title={
                    quota
                      ? 'Four overs already assigned'
                      : adjacent
                        ? 'Assigned to an adjacent over'
                        : names[id]
                  }
                  onClick={() =>
                    onChange({
                      ...plan,
                      bowling_plan: plan.bowling_plan.map((p, i) => (i === over ? id : p)),
                    })
                  }
                >
                  <span>{names[id] || id}</span>
                  <span className="mono">{count}/4</span>
                </button>
              );
            })}
          </div>
          <ServiceNote>
            Any active fielder can be assigned in a manual plan. The optimizer uses the narrower
            recorded bowler/all-rounder role pool.
          </ServiceNote>
        </div>
      )}
      {tab === 'impact' && (
        <div className="impact-workbench">
          <p>
            Only an explicit domestic replacement at the innings interval is supported. First
            nominate up to five substitutes, then choose the outgoing starter and incoming domestic
            substitute.
          </p>
          <div className="substitute-options">
            {roster.members
              .filter((m) => !plan.starting_xi.includes(m.player.player_id))
              .map(({ player: p }) => (
                <TagToggle
                  key={p.player_id}
                  active={plan.substitutes.includes(p.player_id)}
                  disabled={
                    disabled ||
                    (!plan.substitutes.includes(p.player_id) && plan.substitutes.length >= 5)
                  }
                  onClick={() => {
                    const substitutes = plan.substitutes.includes(p.player_id)
                      ? plan.substitutes.filter((id) => id !== p.player_id)
                      : [...plan.substitutes, p.player_id];
                    update({
                      ...plan,
                      substitutes,
                      impact:
                        plan.impact && substitutes.includes(plan.impact.incoming_id)
                          ? plan.impact
                          : null,
                    });
                  }}
                >
                  {p.display_name}
                  {p.is_overseas ? ' · OS' : ''}
                </TagToggle>
              ))}
          </div>
          <div className="impact-columns">
            <div>
              <span className="eyebrow">Outgoing starter</span>
              {plan.starting_xi.map((id) => (
                <TagToggle
                  key={id}
                  active={outgoing === id}
                  disabled={disabled}
                  onClick={() => {
                    setImpactOut(id);
                    const incoming = plan.impact?.incoming_id;
                    if (incoming)
                      update({
                        ...plan,
                        impact: {
                          outgoing_id: id,
                          incoming_id: incoming,
                          timing: 'innings_interval',
                        },
                      });
                  }}
                >
                  {names[id] || id}
                </TagToggle>
              ))}
            </div>
            <div>
              <span className="eyebrow">Incoming domestic substitute</span>
              {plan.substitutes
                .filter(
                  (id) =>
                    roster.members.find((m) => m.player.player_id === id)?.player.is_overseas ===
                    false,
                )
                .map((id) => (
                  <TagToggle
                    key={id}
                    active={plan.impact?.incoming_id === id}
                    disabled={disabled || !plan.starting_xi.includes(outgoing)}
                    onClick={() =>
                      update({
                        ...plan,
                        impact: {
                          outgoing_id: outgoing,
                          incoming_id: id,
                          timing: 'innings_interval',
                        },
                      })
                    }
                  >
                    {names[id] || id}
                  </TagToggle>
                ))}
              {!plan.substitutes.some(
                (id) =>
                  roster.members.find((m) => m.player.player_id === id)?.player.is_overseas ===
                  false,
              ) && <p>Nominate a domestic substitute above to enable a replacement.</p>}
            </div>
          </div>
          <button
            className="text-button"
            disabled={disabled || !plan.impact}
            onClick={() => {
              setImpactOut('');
              update({ ...plan, impact: null });
            }}
          >
            Clear interval replacement ×
          </button>
          <ServiceNote>
            The interval replacement changes only second-innings players. Full supplementary Impact
            regulations and match registration are not verified.
          </ServiceNote>
        </div>
      )}
      <details
        className={`lab-validation ${issues.length ? 'needs-work' : 'passed'}`}
        open={issues.length > 0}
      >
        <summary>
          {issues.length
            ? `${issues.length} plan checks need attention`
            : 'Core plan checks passed'}{' '}
          <span className="mono">{plan.team_id}</span>
        </summary>
        {issues.length > 0 ? (
          <ul>
            {issues.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        ) : (
          <p>
            Roster membership, active players, overseas proxy, keeper and bowling quotas pass local
            checks. The service rechecks every submitted plan.
          </p>
        )}
      </details>
    </section>
  );
}
