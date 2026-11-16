import { useEffect, useRef, useState } from 'react';
import {
  runSimulation,
  SimulationError,
  type CompletedRun,
  type SimulationRequest,
} from './api/simulation';

export type RunState =
  | { phase: 'ready'; run: CompletedRun | null; notice?: string }
  | { phase: 'running'; run: CompletedRun | null }
  | { phase: 'failed'; run: CompletedRun | null; error: SimulationError };

/** Each completion belongs to its immutable submitted inputs; cancelled replies are ignored. */
export function useSimulation(initial: CompletedRun | null) {
  const [state, setState] = useState<RunState>({ phase: 'ready', run: initial });
  const active = useRef<{ controller: AbortController; token: number } | null>(null);
  const generation = useRef(0);
  useEffect(
    () => () => {
      generation.current++;
      active.current?.controller.abort();
    },
    [],
  );
  async function run(request: SimulationRequest) {
    if (active.current) return;
    const controller = new AbortController(),
      token = ++generation.current;
    active.current = { controller, token };
    setState((previous) => ({ phase: 'running', run: previous.run }));
    const timer = window.setTimeout(() => controller.abort(), 45000);
    try {
      const response = await runSimulation(request, controller.signal);
      if (token === generation.current)
        setState({
          phase: 'ready',
          run: { request, response, source: 'api', completedAt: new Date().toISOString() },
        });
    } catch (error) {
      if (token === generation.current)
        setState((previous) => ({
          phase: 'failed',
          run: previous.run,
          error: controller.signal.aborted
            ? new SimulationError(
                'The run did not finish within 45 seconds. Try fewer trials. The backend may still be finishing this request.',
                'timeout',
              )
            : error instanceof SimulationError
              ? error
              : new SimulationError(
                  error instanceof Error ? error.message : 'The simulation could not complete.',
                  'response',
                ),
        }));
    } finally {
      window.clearTimeout(timer);
      if (active.current?.token === token) active.current = null;
    }
  }
  function cancel() {
    generation.current++;
    active.current?.controller.abort();
    active.current = null;
    setState((previous) => ({
      phase: 'ready',
      run: previous.run,
      notice:
        'Stopped waiting. The backend may still finish the submitted run; its result will not replace this board.',
    }));
  }
  function clear() {
    generation.current++;
    active.current?.controller.abort();
    active.current = null;
    setState({ phase: 'ready', run: null });
  }
  function restore(run: CompletedRun) {
    if (!active.current) setState({ phase: 'ready', run });
  }
  return { state, run, cancel, clear, restore };
}
