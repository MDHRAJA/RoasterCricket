import { useEffect, useState } from 'react';
import { fetchRoster, savedRosters } from './api/lab';
export function useLabRosters(a: string, b: string) {
  const [rosters, setRosters] = useState(savedRosters),
    [sources, setSources] = useState<Record<string, 'saved' | 'api'>>({}),
    [attempt, setAttempt] = useState(0),
    [checking, setChecking] = useState(false);
  useEffect(() => {
    const controller = new AbortController(),
      timer = window.setTimeout(() => controller.abort(), 3500);
    setChecking(true);
    Promise.allSettled(
      [a, b].map(async (id) => {
        const roster = await fetchRoster(id, controller.signal);
        if (!controller.signal.aborted) {
          setRosters((old) => ({ ...old, [id]: roster }));
          setSources((old) => ({ ...old, [id]: 'api' }));
        }
      }),
    ).finally(() => {
      if (!controller.signal.aborted) setChecking(false);
      window.clearTimeout(timer);
    });
    const finish = () => setChecking(false);
    controller.signal.addEventListener('abort', finish);
    return () => {
      controller.signal.removeEventListener('abort', finish);
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [a, b, attempt]);
  return { rosters, sources, checking, retry: () => setAttempt((n) => n + 1) };
}
