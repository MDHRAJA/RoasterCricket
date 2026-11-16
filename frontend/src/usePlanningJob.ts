import { useEffect, useRef, useState } from 'react';
type JobState =
  | { phase: 'idle' }
  | { phase: 'running'; label: string }
  | { phase: 'complete'; label: string }
  | { phase: 'cancelled' }
  | { phase: 'failed'; message: string };
export function usePlanningJob() {
  const [state, setState] = useState<JobState>({ phase: 'idle' }),
    generation = useRef(0),
    active = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      generation.current++;
      active.current?.abort();
    },
    [],
  );
  async function start<T>(
    label: string,
    perform: (signal: AbortSignal) => Promise<T>,
    complete: (value: T) => void,
    timeout = 75000,
  ) {
    if (active.current) return;
    const controller = new AbortController(),
      token = ++generation.current;
    active.current = controller;
    setState({ phase: 'running', label });
    const timer = window.setTimeout(() => controller.abort(), timeout);
    try {
      const value = await perform(controller.signal);
      if (token === generation.current) {
        complete(value);
        setState({ phase: 'complete', label });
      }
    } catch (e) {
      if (token === generation.current)
        setState({
          phase: 'failed',
          message: controller.signal.aborted
            ? 'The planning request exceeded its waiting limit. Try fewer trials. The backend may still be finishing it.'
            : e instanceof Error
              ? e.message
              : 'The planning request failed.',
        });
    } finally {
      window.clearTimeout(timer);
      if (token === generation.current) active.current = null;
    }
  }
  function cancel() {
    generation.current++;
    active.current?.abort();
    active.current = null;
    setState({ phase: 'cancelled' });
  }
  return { state, start, cancel, busy: state.phase === 'running' };
}
