import { Fragment, useRef } from 'react';
import type { ArchiveMatch, DataSource } from '../api/contracts';
import {
  formatDate,
  groupMatches,
  overs,
  regularInnings,
  resultLabel,
  score,
  shortGround,
} from '../domain/archive';
import { team } from '../domain/teams';
import { useInnings } from '../hooks';
import { Icon, RouteBullet, ServiceNote, SplitFlap } from './Signs';

export function FeaturedMatch({
  match,
  source,
  onOpen,
}: {
  match: ArchiveMatch;
  source: DataSource;
  onOpen: () => void;
}) {
  const { innings, error } = useInnings(match.match_id, source);
  return (
    <section className="featured" aria-label="Latest match in the current selection">
      <div className="featured-top">
        <span className="eyebrow">
          <span className="square-marker" /> Latest entry
        </span>
        <span className="outline-tag">{match.stage || 'League'}</span>
        <span className="mono featured-date">{formatDate(match.match_date)}</span>
      </div>
      <div className="featured-body">
        <div className="featured-teams">
          {[match.team1_id, match.team2_id].map((id) => {
            const entry = regularInnings(innings, id);
            return (
              <div className="featured-team" key={id}>
                <RouteBullet id={id} />
                <span className="featured-team-name">{team(id).name}</span>
                <div className="featured-score">
                  <SplitFlap
                    value={score(entry)}
                    label={`${team(id).short} ${entry ? `${entry.total_runs} runs, ${entry.wickets} wickets` : 'score unavailable'}`}
                  />
                  <span className="overs">
                    {entry
                      ? `${overs(entry.legal_balls)} overs`
                      : error
                        ? 'Score unavailable'
                        : 'Recorded score'}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
        <div className="featured-outcome">
          <span className="eyebrow">Recorded result</span>
          <h2>{resultLabel(match)}</h2>
          <p>
            {match.city}
            <br />
            <span>{shortGround(match)}</span>
          </p>
          <button className="yellow-button" onClick={onOpen}>
            Open record <Icon name="arrow" />
          </button>
        </div>
      </div>
      <div className="featured-footer">
        <Icon name="stumps" />
        <span>Completed match · historical record</span>
        <span className="mono">REF {match.match_id}</span>
      </div>
    </section>
  );
}

export function DeparturesBoard({
  matches,
  total,
  limit,
  onMore,
  onOpen,
  onReset,
}: {
  matches: ArchiveMatch[];
  total: number;
  limit: number;
  onMore: () => void;
  onOpen: (m: ArchiveMatch) => void;
  onReset: () => void;
}) {
  const buttons = useRef(new Map<string, HTMLButtonElement>());
  const visible = matches.slice(0, limit);
  if (!matches.length)
    return (
      <section className="empty-state">
        <span className="empty-number">00</span>
        <h2>No matches in this selection</h2>
        <p>Try another team, ground or search term.</p>
        <button className="text-button" onClick={onReset}>
          Clear filters <Icon name="arrow" />
        </button>
      </section>
    );
  return (
    <section className="board" aria-label="Match archive board">
      <div className="board-title">
        <h2>Match board</h2>
        <span className="mono">Latest first · {total} records</span>
      </div>
      <table>
        <caption className="sr-only">
          Recorded IPL matches. Use up and down arrows on match buttons to move through rows.
        </caption>
        <thead>
          <tr>
            <th scope="col">Reference</th>
            <th scope="col">Fixture</th>
            <th scope="col">Ground</th>
            <th scope="col">Recorded result</th>
            <th>
              <span className="sr-only">Open</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {groupMatches(visible).map(([date, group]) => (
            <Fragment key={date}>
              <tr className="date-strip">
                <th colSpan={5} scope="rowgroup">
                  <span>{formatDate(date, true)}</span>
                  <span>
                    {group.length} {group.length === 1 ? 'match' : 'matches'}
                  </span>
                </th>
              </tr>
              {group.map((m) => (
                <tr className="match-row" key={m.match_id}>
                  <td className="reference">
                    <span className="mono">{m.match_id}</span>
                    <span className="row-stage">{m.stage || 'League'}</span>
                  </td>
                  <td className="match-pair">
                    <button
                      ref={(el) => {
                        if (el) buttons.current.set(m.match_id, el);
                        else buttons.current.delete(m.match_id);
                      }}
                      className="match-link"
                      onClick={() => onOpen(m)}
                      onKeyDown={(e) => {
                        if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
                        e.preventDefault();
                        const index = visible.findIndex((v) => v.match_id === m.match_id);
                        const next =
                          visible[
                            (index + (e.key === 'ArrowDown' ? 1 : -1) + visible.length) %
                              visible.length
                          ];
                        buttons.current.get(next.match_id)?.focus();
                      }}
                      aria-label={`Open ${team(m.team1_id).name} versus ${team(m.team2_id).name}, ${formatDate(m.match_date)}`}
                    >
                      {[m.team1_id, m.team2_id].map((id) => (
                        <span className="team-row" key={id}>
                          <RouteBullet id={id} small />
                          <span>{team(id).name}</span>
                          {m.winner_id === id && (
                            <span className="winner-mark" aria-label="Winner">
                              ↗
                            </span>
                          )}
                        </span>
                      ))}
                    </button>
                  </td>
                  <td className="ground">
                    <strong>{m.city || 'Ground recorded'}</strong>
                    <span>{shortGround(m)}</span>
                  </td>
                  <td className="row-result">
                    <span className={`result-tag ${!m.winner_id ? 'no-result' : ''}`}>
                      {m.winner_id
                        ? `${m.winner_id} won`
                        : m.result === 'tie'
                          ? 'Tied'
                          : 'No result'}
                    </span>
                    <span className="mono">
                      {m.winner_id
                        ? m.win_by_runs != null
                          ? `${m.win_by_runs} runs`
                          : m.win_by_wickets != null
                            ? `${m.win_by_wickets} wickets`
                            : 'See record'
                        : '—'}
                      {m.result_method ? ` · ${m.result_method}` : ''}
                    </span>
                  </td>
                  <td className="row-arrow">
                    <Icon name="arrow" />
                  </td>
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
      <div className="board-bottom">
        <span className="mono">
          {visible.length} / {total} shown
        </span>
        {visible.length < total ? (
          <button className="text-button" onClick={onMore}>
            Show {Math.min(12, total - visible.length)} more <span aria-hidden="true">↓</span>
          </button>
        ) : (
          <span className="eyebrow">End of selection</span>
        )}
      </div>
      <ServiceNote>
        Archive records only. Match times, live scores and forecasts are not included in this board.
      </ServiceNote>
    </section>
  );
}
