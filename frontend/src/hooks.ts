import { useEffect, useRef, useState } from 'react';
import { liveAdapter, savedInnings, snapshots } from './api/client';
import type { ArchiveInnings, ArchiveMatch, DataSource, Season } from './api/contracts';
import type { Route } from './domain/archive';

/** A new workspace starts at its heading, including after a lazy chunk arrives. */
export function useWorkspaceNavigation(place: Route['place'], matchId: string | null) {
  const key = `${place}/${matchId || ''}`,
    previous = useRef(key);
  useEffect(() => {
    if (previous.current === key) return;
    previous.current = key;
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    const targetId = place === 'fixtures' ? 'board-content' : `${place}-content`;
    const focus = () => {
      const target = document.getElementById(targetId);
      if (!target) return false;
      target.focus({ preventScroll: true });
      return true;
    };
    if (focus()) return;
    const root = document.getElementById('root');
    if (!root) return;
    const observer = new MutationObserver(() => {
      if (focus()) observer.disconnect();
    });
    observer.observe(root, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [key, place]);
}

export function useArchive(season: Season, enabled = true) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{
    season: Season;
    matches: ArchiveMatch[];
    source: DataSource;
    checking: boolean;
  }>({ season, matches: snapshots[season].matches, source: 'snapshot', checking: enabled });
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    let active = true;
    setState({ season, matches: snapshots[season].matches, source: 'snapshot', checking: true });
    const timer = window.setTimeout(() => controller.abort(), 3000);
    liveAdapter
      .getMatches(season, controller.signal)
      .then((matches) => {
        if (active) setState({ season, matches, source: 'api', checking: false });
      })
      .catch(() => {
        if (active)
          setState({
            season,
            matches: snapshots[season].matches,
            source: 'snapshot',
            checking: false,
          });
      })
      .finally(() => window.clearTimeout(timer));
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [season, attempt, enabled]);
  const current =
    state.season === season
      ? state
      : { season, matches: snapshots[season].matches, source: 'snapshot' as const, checking: true };
  return { ...current, retry: () => setAttempt((n) => n + 1) };
}

export function useInnings(matchId: string | undefined, source: DataSource) {
  const [state, setState] = useState<{
    id?: string;
    source: DataSource;
    innings: ArchiveInnings[];
    error: boolean;
  }>({ source: 'snapshot', innings: [], error: false });
  useEffect(() => {
    if (!matchId || source === 'snapshot') return;
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 3000);
    liveAdapter
      .getInnings(matchId, controller.signal)
      .then((innings) => {
        if (active) setState({ id: matchId, source, innings, error: false });
      })
      .catch(() => {
        if (active) setState({ id: matchId, source, innings: [], error: true });
      })
      .finally(() => window.clearTimeout(timer));
    return () => {
      active = false;
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [matchId, source]);
  if (!matchId) return { innings: [], error: false };
  if (source === 'snapshot') return { innings: savedInnings(matchId), error: false };
  return state.id === matchId && state.source === source ? state : { innings: [], error: false };
}

export function useTheme() {
  const [theme, setTheme] = useState(
    document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light',
  );
  function toggle() {
    const next = theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem('concourse-theme', next);
    } catch {
      /* Theme remains usable without storage. */
    }
    setTheme(next);
  }
  return { theme, toggle };
}
