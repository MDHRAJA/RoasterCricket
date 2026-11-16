import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react';
import type { ArchiveMatch, DataSource } from '../api/contracts';
import { formatDate, overs, regularInnings, resultLabel, shortGround } from '../domain/archive';
import { team } from '../domain/teams';
import { useInnings } from '../hooks';
import { Icon, RouteBullet, ServiceNote } from './Signs';

function useModalDialog(
  ref: RefObject<HTMLDialogElement | null>,
  input?: RefObject<HTMLInputElement | null>,
) {
  useLayoutEffect(() => {
    const node = ref.current,
      origin = document.activeElement,
      route = window.location.hash;
    node?.showModal();
    input?.current?.focus();
    return () => {
      node?.close();
      if (window.location.hash === route && origin instanceof HTMLElement && origin.isConnected)
        origin.focus({ preventScroll: true });
    };
  }, [ref, input]);
}

export function MatchRecord({
  match,
  missing,
  source,
  onClose,
}: {
  match?: ArchiveMatch;
  missing: boolean;
  source: DataSource;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const { innings, error } = useInnings(match?.match_id, source);
  useModalDialog(ref);
  return (
    <dialog
      ref={ref}
      className="record-dialog"
      aria-labelledby="record-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="dialog-header">
        <span className="eyebrow">02 / Match record</span>
        <button className="icon-button" onClick={onClose} aria-label="Close match record">
          <Icon name="close" />
        </button>
      </div>
      {match ? (
        <>
          <div className="record-heading">
            <span className="eyebrow">
              {formatDate(match.match_date)} · {match.stage || 'League'}
            </span>
            <h2 id="record-title">
              {team(match.team1_id).short}
              <span className="muted"> v </span>
              {team(match.team2_id).short}
            </h2>
            <p>
              {shortGround(match)} · {match.city}
            </p>
          </div>
          <div className="record-scoreboard">
            {[match.team1_id, match.team2_id].map((id) => {
              const entry = regularInnings(innings, id);
              return (
                <div className="record-team" key={id}>
                  <RouteBullet id={id} />
                  <strong>{team(id).name}</strong>
                  <span className="record-score mono">
                    {entry ? `${entry.total_runs}/${entry.wickets}` : '—'}
                    <small>
                      {entry
                        ? `${overs(entry.legal_balls)} overs`
                        : error
                          ? 'Unavailable'
                          : source === 'api'
                            ? 'Loading score'
                            : 'No innings recorded'}
                    </small>
                  </span>
                </div>
              );
            })}
          </div>
          {innings.some((i) => i.is_super_over) && (
            <div className="super-over">
              <span className="eyebrow">Super over</span>
              {innings
                .filter((i) => i.is_super_over)
                .map((i) => (
                  <span className="mono" key={i.innings}>
                    {i.batting_team_id} {i.total_runs}/{i.wickets} ({overs(i.legal_balls)})
                  </span>
                ))}
            </div>
          )}
          <p className="record-result">{resultLabel(match)}</p>
          <dl className="record-facts">
            <div>
              <dt>Toss</dt>
              <dd>
                {match.toss_winner_id
                  ? `${team(match.toss_winner_id).short} · chose to ${match.toss_decision}`
                  : 'Not recorded'}
              </dd>
            </div>
            <div>
              <dt>Allocation</dt>
              <dd>{match.scheduled_overs} overs per side</dd>
            </div>
            <div>
              <dt>Reference</dt>
              <dd className="mono">{match.match_id}</dd>
            </div>
            <div>
              <dt>Source</dt>
              <dd>{source === 'api' ? 'Local archive API' : 'Saved archive snapshot'}</dd>
            </div>
          </dl>
          <ServiceNote>
            Historical result. This record does not contain a pre-match prediction.
          </ServiceNote>
        </>
      ) : (
        <div className="empty-state">
          <h2 id="record-title">{missing ? 'Record not found' : 'Opening archive'}</h2>
          <p>
            {missing
              ? 'This reference is not in the selected season.'
              : 'Retrieving the match record.'}
          </p>
          <button className="text-button" onClick={onClose}>
            Return to fixtures <Icon name="arrow" />
          </button>
        </div>
      )}
      <div className="dialog-bottom">
        <button className="text-button" onClick={onClose}>
          ← Back to fixtures
        </button>
        <span className="mono">ESC</span>
      </div>
    </dialog>
  );
}

type Command = {
  id: string;
  title: string;
  detail: string;
  kind: 'Match' | 'Team' | 'Ground';
  run: () => void;
};
export function CommandKiosk({
  matches,
  onClose,
  onMatch,
  onTeam,
  onVenue,
}: {
  matches: ArchiveMatch[];
  onClose: () => void;
  onMatch: (m: ArchiveMatch) => void;
  onTeam: (id: string) => void;
  onVenue: (id: string) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState(0);
  const commands: Command[] = [];
  const teamIds = [...new Set(matches.flatMap((m) => [m.team1_id, m.team2_id]))].sort();
  for (const id of teamIds)
    commands.push({
      id: `team-${id}`,
      title: `${id} · ${team(id).name}`,
      detail: 'Filter the board',
      kind: 'Team',
      run: () => onTeam(id),
    });
  const venues = new Map(matches.map((m) => [m.venue_id, m]));
  for (const [id, m] of venues)
    commands.push({
      id: `venue-${id}`,
      title: shortGround(m),
      detail: m.city || 'Filter by ground',
      kind: 'Ground',
      run: () => onVenue(id),
    });
  for (const m of matches)
    commands.push({
      id: m.match_id,
      title: `${m.team1_id} v ${m.team2_id}`,
      detail: `${formatDate(m.match_date)} · ${m.city} · ${m.match_id}`,
      kind: 'Match',
      run: () => onMatch(m),
    });
  const q = query.toLowerCase().trim();
  const results = (
    q
      ? commands.filter((c) => `${c.title} ${c.detail} ${c.kind}`.toLowerCase().includes(q))
      : commands.filter((c) => c.kind === 'Match')
  ).slice(0, 18);
  const selected = Math.min(index, Math.max(0, results.length - 1));
  function run(command: Command) {
    onClose();
    command.run();
  }
  useModalDialog(ref, input);
  useEffect(() => {
    document.getElementById(`command-${selected}`)?.scrollIntoView({ block: 'nearest' });
  }, [selected]);
  return (
    <dialog
      ref={ref}
      className="command-dialog"
      aria-labelledby="command-title"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="dialog-header">
        <h2 id="command-title" className="eyebrow">
          Information / Search the archive
        </h2>
        <button className="icon-button" onClick={onClose} aria-label="Close search">
          <Icon name="close" />
        </button>
      </div>
      <div className="command-input">
        <Icon name="search" />
        <input
          ref={input}
          value={query}
          placeholder="Match, team, ground or reference…"
          aria-label="Search archive commands"
          role="combobox"
          aria-expanded="true"
          aria-controls="command-results"
          aria-autocomplete="list"
          aria-activedescendant={results.length ? `command-${selected}` : undefined}
          onChange={(e) => {
            setQuery(e.target.value);
            setIndex(0);
          }}
          onKeyDown={(e) => {
            if (['ArrowDown', 'ArrowUp'].includes(e.key)) {
              e.preventDefault();
              setIndex(
                (selected + (e.key === 'ArrowDown' ? 1 : -1) + results.length) %
                  Math.max(1, results.length),
              );
            }
            if (e.key === 'Enter' && results[selected]) {
              e.preventDefault();
              run(results[selected]);
            }
          }}
        />
      </div>
      <div
        className="command-results"
        id="command-results"
        role="listbox"
        aria-label="Archive results"
      >
        {results.map((c, i) => (
          <div
            id={`command-${i}`}
            key={c.id}
            role="option"
            aria-selected={i === selected}
            className={`command-result ${i === selected ? 'selected' : ''}`}
            onPointerMove={() => setIndex(i)}
            onClick={() => run(c)}
          >
            <span>
              <strong>{c.title}</strong>
              <small>{c.detail}</small>
            </span>
            <span className="command-kind">{c.kind} →</span>
          </div>
        ))}
        {!results.length && (
          <p className="command-empty">No matching records. Try a team code or a city.</p>
        )}
      </div>
      <div className="dialog-bottom mono">
        <span>↑ ↓ Navigate · Enter Open</span>
        <span>ESC Close</span>
      </div>
    </dialog>
  );
}
