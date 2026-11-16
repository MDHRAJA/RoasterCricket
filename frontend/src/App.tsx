import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { snapshots } from './api/client';
import type { ArchiveMatch } from './api/contracts';
import {
  filterMatches,
  initialFilters,
  parseRoute,
  routeHash,
  shortGround,
  type BoardFilters,
  type StageFilter,
} from './domain/archive';
import { team } from './domain/teams';
import { useArchive, useTheme, useWorkspaceNavigation } from './hooks';
import { CommandKiosk } from './components/Dialogs';
import { EXAMPLE_ID } from './domain/simulation';
import { DeparturesBoard, FeaturedMatch } from './components/DeparturesBoard';
import { LineKey } from './components/LineKey';
import { usePlanning } from './PlanningContext';
import type { LabSlot, SlotId } from './domain/lab';
import type { CompletedRun, SimulationRequest } from './api/simulation';
import { Icon, RouteBullet, ServiceNote, SignPanel, TagToggle } from './components/Signs';

const MatchWorkspace = lazy(() => import('./components/MatchWorkspace'));
const LabWorkspace = lazy(() => import('./components/LabWorkspace'));
const RecordWorkspace = lazy(() => import('./components/RecordWorkspace'));

export default function App() {
  const planning = usePlanning();
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useWorkspaceNavigation(route.place, route.matchId);
  const [query, setQuery] = useState('');
  const [expanded, setExpanded] = useState<'team' | 'venue' | null>(null);
  const [commandOpen, setCommandOpen] = useState(false);
  const [lastMatch, setLastMatch] = useState<string | null>(null);
  const [limit, setLimit] = useState(12);
  const { theme, toggle } = useTheme();
  const { matches, source, checking, retry } = useArchive(
    route.filters.season,
    route.place !== 'record',
  );
  const filters = { ...route.filters, query };
  const filtered = useMemo(() => filterMatches(matches, filters), [matches, route.filters, query]);
  const selected =
    route.place === 'match' ? matches.find((m) => m.match_id === route.matchId) : undefined;
  const rememberedMatch = matches.find((m) => m.match_id === lastMatch);
  const teamIds = [...new Set(matches.flatMap((m) => [m.team1_id, m.team2_id]))].sort();
  const venues = [...new Map(matches.map((m) => [m.venue_id, m])).values()].sort((a, b) =>
    (a.city || '').localeCompare(b.city || ''),
  );
  function navigate(
    place: 'fixtures' | 'match' | 'lab' | 'record',
    next = filters,
    matchId?: string,
  ) {
    window.location.hash = routeHash(place, next, matchId);
  }
  function update(change: Partial<BoardFilters>) {
    if (change.season && change.season !== filters.season) setLastMatch(null);
    navigate('fixtures', { ...filters, ...change });
    setLimit(12);
  }
  function reset() {
    setQuery('');
    setExpanded(null);
    update({ ...initialFilters, season: filters.season });
  }
  function openMatch(m: ArchiveMatch) {
    setLastMatch(m.match_id);
    navigate('match', filters, m.match_id);
  }
  function closeMatch() {
    navigate('fixtures');
  }
  function openExample() {
    setLastMatch(EXAMPLE_ID);
    navigate('match', { ...initialFilters, season: 2026 }, EXAMPLE_ID);
  }
  const labSlot: SlotId | null =
    route.matchId === 'lab-a' ? 'A' : route.matchId === 'lab-b' ? 'B' : null;
  const externalScenario = labSlot && planning.slots ? planning.slots[labSlot] : undefined;
  function openLab() {
    navigate('lab', { ...initialFilters, season: 2026 });
  }
  function openRecord() {
    navigate('record', { ...initialFilters, season: 2026 });
  }
  function openLabMatch(id: SlotId) {
    setLastMatch(`lab-${id.toLowerCase()}`);
    navigate('match', { ...initialFilters, season: 2026 }, `lab-${id.toLowerCase()}`);
  }
  function openRemembered() {
    if (route.place === 'lab' && planning.slots) {
      openLabMatch(planning.active);
      return;
    }
    if (route.place === 'match') {
      navigate('match', filters, route.matchId);
      return;
    }
    if (lastMatch === 'lab-a' || lastMatch === 'lab-b') {
      if (planning.slots) {
        navigate('match', { ...initialFilters }, lastMatch);
        return;
      }
    }
    if (rememberedMatch) navigate('match', filters, rememberedMatch.match_id);
    else openExample();
  }
  function editInLab(
    request: SimulationRequest,
    run: CompletedRun | null,
    names: Record<string, string>,
    venueName: string,
  ) {
    const id = labSlot || 'A';
    const slot: LabSlot = {
      request,
      run,
      names,
      venueName,
      toss:
        planning.slots?.[id].request.batting_first_team_id === request.batting_first_team_id
          ? planning.slots[id].toss
          : { winnerId: request.batting_first_team_id, decision: 'bat' },
    };
    planning.load(id, slot);
    planning.setActive(id);
    openLab();
  }
  useEffect(() => {
    const listener = () => {
      setRoute(parseRoute(window.location.hash));
      setLimit(12);
    };
    window.addEventListener('hashchange', listener);
    return () => window.removeEventListener('hashchange', listener);
  }, []);
  useEffect(() => {
    document.title = `${route.place === 'record' ? 'Record' : route.place === 'lab' ? 'Lab' : labSlot ? `Lab scenario ${labSlot}` : route.place === 'match' && route.matchId === EXAMPLE_ID ? 'CSK v MI / Scenario' : selected ? `${selected.team1_id} v ${selected.team2_id}` : 'Fixtures'} — The Concourse`;
  }, [selected, route.place, route.matchId]);
  useEffect(() => {
    function keyboard(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      const typing = target.matches('input, textarea, select') || target.isContentEditable;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setCommandOpen((v) => !v);
        return;
      }
      if (
        typing ||
        e.metaKey ||
        e.ctrlKey ||
        e.altKey ||
        commandOpen ||
        document.querySelector('dialog[open]')
      )
        return;
      if (e.key === '/') {
        e.preventDefault();
        setCommandOpen(true);
      }
      if (e.key === '1') navigate('fixtures');
      if (e.key === '2') openRemembered();
      if (e.key === '3') openLab();
      if (e.key === '4') openRecord();
    }
    window.addEventListener('keydown', keyboard);
    return () => window.removeEventListener('keydown', keyboard);
  });
  const count = String(filtered.length).padStart(2, '0');
  return (
    <>
      <a
        className="skip-link"
        href={
          route.place === 'record'
            ? '#record-content'
            : route.place === 'lab'
              ? '#lab-content'
              : route.place === 'match'
                ? '#match-content'
                : '#board-content'
        }
        onClick={(e) => {
          e.preventDefault();
          document
            .getElementById(
              route.place === 'record'
                ? 'record-content'
                : route.place === 'lab'
                  ? 'lab-content'
                  : route.place === 'match'
                    ? 'match-content'
                    : 'board-content',
            )
            ?.focus();
        }}
      >
        {route.place === 'record'
          ? 'Skip to Record'
          : route.place === 'lab'
            ? 'Skip to Lab'
            : route.place === 'match'
              ? 'Skip to Match workspace'
              : 'Skip to match board'}
      </a>
      <LineKey
        selected={route.place === 'match'}
        matchAvailable={true}
        labSelected={route.place === 'lab'}
        onLab={openLab}
        recordSelected={route.place === 'record'}
        onRecord={openRecord}
        onFixtures={closeMatch}
        onMatch={openRemembered}
        onCommand={() => setCommandOpen(true)}
        theme={theme}
        onTheme={toggle}
      />
      {route.place === 'fixtures' && (
        <main className="concourse">
          <header className="page-header">
            <div className="page-heading">
              <div className="eyebrow">
                The Concourse <span className="header-divider">/</span> IPL research
              </div>
              <h1>
                Fixtures
                <span className="heading-arrow" aria-hidden="true">
                  ↘
                </span>
              </h1>
              <div className="header-subline">
                <span className="solid-tag">Match archive</span>
                <span className="mono">{filters.season} season</span>
              </div>
            </div>
            <div className="header-count">
              <span className="eyebrow">In this selection</span>
              <strong>{count}</strong>
              <span className="mono">recorded matches</span>
            </div>
            <button
              className="mobile-theme icon-button"
              onClick={toggle}
              aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
            >
              <Icon name={theme === 'dark' ? 'sun' : 'moon'} />
            </button>
          </header>
          <div className="source-strip">
            <span className="source-label">
              <span className={`source-dot ${source === 'api' ? 'connected' : ''}`} />
              {source === 'api' ? 'Local archive API' : 'Saved archive snapshot'}
            </span>
            <span className="source-explainer">Recorded results · not a live feed</span>
            <button className="scenario-entry" onClick={openExample}>
              CSK v MI simulation <span aria-hidden="true">→</span>
            </button>
            <button onClick={retry} disabled={checking}>
              {checking ? 'Checking connection…' : 'Check connection'}{' '}
              <span aria-hidden="true">↗</span>
            </button>
          </div>
          <section className="filter-panel" aria-label="Filter match archive">
            <div className="filter-top">
              <div className="filter-group" aria-label="Season">
                {([2026, 2025] as const).map((season) => (
                  <TagToggle
                    key={season}
                    active={filters.season === season}
                    onClick={() => {
                      setQuery('');
                      setExpanded(null);
                      update({ ...initialFilters, season });
                    }}
                  >
                    {season}
                  </TagToggle>
                ))}
              </div>
              <span className="filter-separator" />
              <div className="filter-group" aria-label="Match category">
                {(
                  [
                    ['all', 'All matches'],
                    ['playoffs', 'Playoffs'],
                    ['league', 'League'],
                    ['no-result', 'No result'],
                  ] as [StageFilter, string][]
                ).map(([id, label]) => (
                  <TagToggle
                    active={filters.stage === id}
                    key={id}
                    onClick={() => update({ stage: id })}
                  >
                    {label}
                  </TagToggle>
                ))}
              </div>
              <button
                className="search-launch"
                aria-label="Find a record, slash shortcut"
                onClick={() => setCommandOpen(true)}
              >
                <Icon name="search" />
                <span>Find a record</span>
                <kbd>/</kbd>
              </button>
            </div>
            <div className="filter-bottom">
              <div className="filter-group">
                <TagToggle
                  active={!!filters.team || expanded === 'team'}
                  aria-expanded={expanded === 'team'}
                  aria-controls="team-options"
                  onClick={() => setExpanded(expanded === 'team' ? null : 'team')}
                >
                  Team {filters.team || '— All'}{' '}
                  <span aria-hidden="true">{expanded === 'team' ? '−' : '+'}</span>
                </TagToggle>
                <TagToggle
                  active={!!filters.venue || expanded === 'venue'}
                  aria-expanded={expanded === 'venue'}
                  aria-controls="venue-options"
                  onClick={() => setExpanded(expanded === 'venue' ? null : 'venue')}
                >
                  Ground {filters.venue ? '— Selected' : '— All'}{' '}
                  <span aria-hidden="true">{expanded === 'venue' ? '−' : '+'}</span>
                </TagToggle>
              </div>
              <label className="board-search">
                <Icon name="search" />
                <input
                  aria-label="Filter the board"
                  placeholder="Filter this board…"
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value);
                    setLimit(12);
                  }}
                />
                {query && (
                  <button aria-label="Clear board search" onClick={() => setQuery('')}>
                    <Icon name="close" />
                  </button>
                )}
              </label>
              {(filters.team || filters.venue || filters.stage !== 'all' || query) && (
                <button className="reset-button" onClick={reset}>
                  Reset <span aria-hidden="true">×</span>
                </button>
              )}
            </div>
            {expanded === 'team' && (
              <div className="expanded-filters team-options" id="team-options">
                <TagToggle active={!filters.team} onClick={() => update({ team: '' })}>
                  All teams
                </TagToggle>
                {teamIds.map((id) => (
                  <TagToggle
                    active={filters.team === id}
                    onClick={() => update({ team: filters.team === id ? '' : id })}
                    key={id}
                  >
                    <RouteBullet id={id} small />
                    {team(id).short}
                  </TagToggle>
                ))}
              </div>
            )}
            {expanded === 'venue' && (
              <div className="expanded-filters venue-options" id="venue-options">
                <TagToggle active={!filters.venue} onClick={() => update({ venue: '' })}>
                  All grounds
                </TagToggle>
                {venues.map((m) => (
                  <TagToggle
                    active={filters.venue === m.venue_id}
                    onClick={() =>
                      update({ venue: filters.venue === m.venue_id ? '' : m.venue_id })
                    }
                    key={m.venue_id}
                  >
                    {m.city} · {shortGround(m)}
                  </TagToggle>
                ))}
              </div>
            )}
          </section>
          <div className="content-grid" id="board-content" tabIndex={-1}>
            <div className="primary-column">
              {filtered[0] && (
                <FeaturedMatch
                  match={filtered[0]}
                  source={source}
                  onOpen={() => openMatch(filtered[0])}
                />
              )}
              <DeparturesBoard
                matches={filtered}
                total={filtered.length}
                limit={limit}
                onMore={() => setLimit((n) => n + 12)}
                onOpen={openMatch}
                onReset={reset}
              />
            </div>
            <aside className="information-column" aria-label="Team key and archive notes">
              <SignPanel className="team-key">
                <div className="aside-heading">
                  <h2>Team key</h2>
                  <span className="mono">{teamIds.length} lines</span>
                </div>
                {teamIds.map((id) => (
                  <button
                    key={id}
                    className={`team-key-row ${filters.team === id ? 'selected' : ''}`}
                    aria-pressed={filters.team === id}
                    onClick={() => update({ team: filters.team === id ? '' : id })}
                  >
                    <RouteBullet id={id} small />
                    <span>{team(id).short}</span>
                    <span className="mono">
                      {String(
                        matches.filter((m) => [m.team1_id, m.team2_id].includes(id)).length,
                      ).padStart(2, '0')}
                    </span>
                  </button>
                ))}
                <p className="team-key-note">Select a line to filter the board.</p>
              </SignPanel>
              <SignPanel className="archive-note">
                <Icon name="pitch" />
                <h2>Read the record.</h2>
                <p>
                  Scores and results from the saved IPL dataset. Every entry opens to its match
                  facts.
                </p>
                <ServiceNote>No pre-match forecasts on this board.</ServiceNote>
              </SignPanel>
              <SignPanel className="provenance">
                <span className="eyebrow">Archive information</span>
                <dl>
                  <div>
                    <dt>Season</dt>
                    <dd>{filters.season}</dd>
                  </div>
                  <div>
                    <dt>Records</dt>
                    <dd>{matches.length}</dd>
                  </div>
                  <div>
                    <dt>Snapshot saved</dt>
                    <dd>{snapshots[filters.season].exported_at.slice(0, 10)}</dd>
                  </div>
                </dl>
                <p>
                  Project dataset sourced from Cricsheet. Coverage reflects saved records, not an
                  official fixture list.
                </p>
              </SignPanel>
            </aside>
          </div>
          <footer className="page-footer">
            <span>The Concourse / IPL research</span>
            <span className="mono">Archive edition · 01</span>
          </footer>
        </main>
      )}
      {route.place === 'match' && (
        <Suspense
          fallback={
            <main className="concourse">
              <div className="empty-state" role="status">
                <h2>Opening Match workspace</h2>
              </div>
            </main>
          }
        >
          <MatchWorkspace
            key={route.matchId}
            match={selected}
            example={route.matchId === EXAMPLE_ID}
            missing={!checking && !selected}
            source={source}
            scenario={externalScenario}
            expiredScenario={Boolean(labSlot && !externalScenario)}
            scenarioLabel={labSlot ? `Lab scenario ${labSlot}` : undefined}
            onBack={labSlot ? openLab : closeMatch}
            backLabel={labSlot ? 'Lab' : 'Fixtures'}
            onEditLab={editInLab}
            onScenarioRun={
              labSlot
                ? (run) => {
                    planning.edit(
                      labSlot,
                      run.request,
                      planning.slots?.[labSlot].request.batting_first_team_id ===
                        run.request.batting_first_team_id
                        ? planning.slots[labSlot].toss
                        : {
                            winnerId: run.request.batting_first_team_id,
                            decision: 'bat',
                          },
                    );
                    planning.complete(labSlot, run);
                  }
                : undefined
            }
            onExample={openExample}
            theme={theme}
            onTheme={toggle}
          />
        </Suspense>
      )}
      {route.place === 'lab' && (
        <Suspense
          fallback={
            <main className="concourse">
              <div className="empty-state" role="status">
                <h2>Opening Lab</h2>
              </div>
            </main>
          }
        >
          <LabWorkspace theme={theme} onTheme={toggle} onMatch={openLabMatch} />
        </Suspense>
      )}
      {route.place === 'record' && (
        <Suspense
          fallback={
            <main className="concourse">
              <div className="empty-state" role="status">
                <h2>Opening Record</h2>
              </div>
            </main>
          }
        >
          <RecordWorkspace theme={theme} onTheme={toggle} />
        </Suspense>
      )}
      {commandOpen && (
        <CommandKiosk
          matches={filterMatches(matches, { ...initialFilters, season: filters.season })}
          onClose={() => setCommandOpen(false)}
          onMatch={openMatch}
          onTeam={(id) => {
            setQuery('');
            update({ team: id, venue: '', stage: 'all' });
          }}
          onVenue={(id) => {
            setQuery('');
            update({ venue: id, team: '', stage: 'all' });
          }}
        />
      )}
    </>
  );
}
