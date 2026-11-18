// @vitest-environment jsdom
import { act, type ComponentProps } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import MatchWorkspace from './MatchWorkspace';
import { OverLine } from './SimulationCharts';
import { exampleRequest, savedRun, savedScenario } from '../api/simulation';
import { snapshots } from '../api/client';

let root: Root;
let container: HTMLDivElement;
let post: Mock<(url: string, init: RequestInit) => Promise<ReturnType<typeof response>>>;
let downloads: Blob[];
const copy = <T,>(value: T): T => JSON.parse(JSON.stringify(value));
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
const response = (body: unknown = savedScenario.response, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
});

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {}
    },
  );
  Object.defineProperty(Element.prototype, 'scrollIntoView', {
    configurable: true,
    value: vi.fn(),
  });
  Object.defineProperties(HTMLDialogElement.prototype, {
    showModal: {
      configurable: true,
      value: function (this: HTMLDialogElement) {
        this.setAttribute('open', '');
      },
    },
    close: {
      configurable: true,
      value: function (this: HTMLDialogElement) {
        this.removeAttribute('open');
      },
    },
  });
  post = vi.fn().mockResolvedValue(response());
  vi.stubGlobal(
    'fetch',
    vi.fn((input: string, init?: RequestInit) =>
      init?.method === 'POST'
        ? post(input, init)
        : Promise.resolve(response({ data: { members: [] } })),
    ),
  );
  downloads = [];
  vi.spyOn(URL, 'createObjectURL').mockImplementation((blob) => {
    downloads.push(blob as Blob);
    return 'blob:test';
  });
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
async function mount(props: Partial<ComponentProps<typeof MatchWorkspace>> = {}) {
  await act(async () =>
    root.render(
      <MatchWorkspace
        example
        missing={false}
        source="snapshot"
        onBack={vi.fn()}
        onExample={vi.fn()}
        theme="light"
        onTheme={vi.fn()}
        {...props}
      />,
    ),
  );
}
function button(text: string, scope: ParentNode = container) {
  const node = [...scope.querySelectorAll<HTMLButtonElement>('button')].find((b) =>
    b.textContent?.replace(/\s+/g, ' ').trim().includes(text),
  );
  if (!node) throw new Error(`Missing button: ${text}`);
  return node;
}
async function click(node: HTMLElement) {
  await act(async () => node.click());
}
async function type(node: HTMLInputElement | HTMLTextAreaElement, value: string) {
  await act(async () => {
    const prototype =
      node instanceof HTMLTextAreaElement
        ? HTMLTextAreaElement.prototype
        : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(prototype, 'value')!.set!.call(node, value);
    node.dispatchEvent(new Event('input', { bubbles: true }));
  });
}
const status = () => container.querySelector('.run-status')!.textContent!;
const seed = () => container.querySelector<HTMLInputElement>('.seed-control input')!;
const json = () => container.querySelector<HTMLTextAreaElement>('#scenario-json')!;
async function exported() {
  return JSON.parse(
    await new Promise<string>((resolve) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.readAsText(downloads.at(-1)!);
    }),
  );
}

describe('Phase 2: Match simulation workflow', () => {
  it('labels the saved example and keeps its exact receipt, XI and histogram counts', async () => {
    await mount();
    expect(status()).toContain('Saved run displayed');
    expect(container.textContent).toContain('not historically calibrated');
    expect(container.querySelectorAll('.plan-order li')).toHaveLength(11);
    for (const [index, innings] of savedRun.response.data.innings.entries()) {
      const counts = [...container.querySelectorAll('.bin-counts tbody tr')].map((row) =>
        Number(row.querySelectorAll('td')[index].textContent),
      );
      expect(counts.reduce((a, b) => a + b, 0)).toBe(savedRun.request.simulations);
      expect(container.querySelectorAll('.distribution-identity')[index].textContent).toContain(
        innings.mean_runs.toFixed(1),
      );
    }
    expect(post).not.toHaveBeenCalled();
  });

  it('keeps old odds and receipt when settings change, then submits seed zero exactly', async () => {
    await mount();
    const oldOdds = container.querySelector('.verdict-board')!.textContent;
    await type(seed(), '0');
    await click(container.querySelector<HTMLInputElement>('.availability-control input')!);
    expect(status()).toContain('Inputs changed');
    expect(container.querySelector('.verdict-board')!.textContent).toBe(oldOdds);
    const body = copy(savedScenario.response);
    body.data.seed = 0;
    post.mockResolvedValue(response(body));
    await click(button('Run simulation'));
    const request = JSON.parse(String(post.mock.calls[0][1].body));
    expect(request).toEqual({ ...exampleRequest, seed: 0, allow_unknown_availability: false });
    expect(status()).toContain('New run complete');
    expect(status()).toContain('seed 0');
  });

  it.each(['', '-1', '1.5', '4294967296', 'abc'])(
    'blocks invalid seed %j without posting',
    async (value) => {
      await mount();
      await type(seed(), value);
      expect(seed().getAttribute('aria-invalid')).toBe('true');
      expect(button('Run simulation').disabled).toBe(true);
      await click(button('Run simulation'));
      expect(post).not.toHaveBeenCalled();
    },
  );

  it('locks inputs, blocks double submissions, ignores a cancelled late response, and retries', async () => {
    const pending = deferred<ReturnType<typeof response>>();
    post.mockReturnValueOnce(pending.promise);
    await mount();
    const runButton = button('Run simulation');
    await act(async () => {
      runButton.click();
      runButton.click();
    });
    expect(status()).toContain('Simulation in progress');
    expect(post).toHaveBeenCalledTimes(1);
    expect(seed().disabled).toBe(true);
    expect(button('50').disabled).toBe(true);
    expect(button('Load request').disabled).toBe(true);
    const signal = post.mock.calls[0][1].signal as AbortSignal;
    await click(button('Stop waiting'));
    expect(signal.aborted).toBe(true);
    await click(button('Run simulation'));
    expect(status()).toContain('New run complete');
    await act(async () => pending.resolve(response({ invalid: true })));
    expect(status()).toContain('New run complete');
    expect(post).toHaveBeenCalledTimes(2);
  });

  it('times out at 45 seconds, keeps the old result, and allows a retry', async () => {
    vi.useFakeTimers();
    post.mockImplementationOnce(
      (_url: string, init: RequestInit) =>
        new Promise((_yes, no) =>
          init.signal!.addEventListener('abort', () =>
            no(new DOMException('Aborted', 'AbortError')),
          ),
        ),
    );
    await mount();
    await click(button('Run simulation'));
    await act(async () => vi.advanceTimersByTimeAsync(45000));
    expect(status()).toContain('45 seconds');
    expect(container.querySelector('.run-source-tag')!.textContent).toBe('Saved output');
    await click(button('Run simulation'));
    expect(status()).toContain('New run complete');
  });

  it('aborts the pending request on navigation away and never publishes its late result', async () => {
    const pending = deferred<ReturnType<typeof response>>();
    post.mockReturnValueOnce(pending.promise);
    const onScenarioRun = vi.fn();
    await mount({ onScenarioRun });
    await click(button('Run simulation'));
    const signal = post.mock.calls[0][1].signal as AbortSignal;
    await act(async () => root.render(<div>Another workspace</div>));
    expect(signal.aborted).toBe(true);
    await act(async () => pending.resolve(response()));
    expect(onScenarioRun).not.toHaveBeenCalled();
    expect(container.textContent).toBe('Another workspace');
  });

  it.each([422, 429, 500])(
    'shows HTTP %i failures and preserves the previous run',
    async (code) => {
      post.mockResolvedValue(
        response(
          {
            error: {
              code: 'invalid_plan',
              message: 'Plan rejected',
              details: [{ location: ['body', 'team_a'], message: 'Check lineup' }],
            },
          },
          code,
        ),
      );
      await mount();
      await click(button('Run simulation'));
      expect(status()).toContain('Run not completed');
      expect(status()).toContain(code === 429 ? 'Another planning run' : 'Plan rejected');
      expect(status()).toContain('team_a: Check lineup');
      expect(container.querySelector('.run-source-tag')!.textContent).toBe('Saved output');
    },
  );

  it('handles offline and corrupt responses, then recovers with a new run', async () => {
    post
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(response({ data: {} }));
    await mount();
    await click(button('Run simulation'));
    expect(status()).toContain('unavailable');
    await click(button('Run simulation'));
    expect(status()).toContain('Run not completed');
    expect(container.querySelector('.verdict-board')).not.toBeNull();
    await click(button('Run simulation'));
    expect(status()).toContain('New run complete');
  });

  it('runs with Space outside controls but ignores typing and repeated keys', async () => {
    await mount();
    const key = async (node: HTMLElement, repeat = false) =>
      act(async () => {
        node.dispatchEvent(
          new KeyboardEvent('keydown', {
            code: 'Space',
            key: ' ',
            bubbles: true,
            cancelable: true,
            repeat,
          }),
        );
      });
    await key(seed());
    await key(json());
    await key(document.body, true);
    expect(post).not.toHaveBeenCalled();
    await key(document.body);
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('rejects malformed, oversized and mismatched imports without losing the displayed run', async () => {
    await mount();
    for (const [raw, error] of [
      ['{bad', 'not valid JSON'],
      ['x'.repeat(65537), '64 KB'],
      [JSON.stringify({ ...exampleRequest, venue_id: 'wrong' }), 'both teams'],
    ]) {
      await type(json(), raw);
      await click(button('Load request'));
      expect(container.querySelector('[role="alert"]')!.textContent).toContain(error);
      expect(status()).toContain('Saved run displayed');
    }
    expect(post).not.toHaveBeenCalled();
  });

  it('imports a valid intermediate trial count, clears old results and restores the saved example', async () => {
    await mount();
    await type(json(), JSON.stringify({ ...exampleRequest, simulations: 75 }));
    await click(button('Load request'));
    expect(status()).toContain('Scenario loaded');
    expect(container.querySelector('.verdict-board')).toBeNull();
    expect(container.textContent).toContain('75 trials from imported request');
    await click(button('Restore saved example'));
    expect(status()).toContain('Saved run displayed');
    expect(seed().value).toBe(String(exampleRequest.seed));
  });

  it('imports a request file, and permits choosing the same file again', async () => {
    await mount();
    const file = new File([JSON.stringify(exampleRequest)], 'request.json', {
      type: 'application/json',
    });
    Object.defineProperty(file, 'text', {
      value: async () => JSON.stringify({ ...exampleRequest, seed: 9 }),
    });
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    Object.defineProperty(input, 'files', { configurable: true, value: [file] });
    await act(async () => input.dispatchEvent(new Event('change', { bubbles: true })));
    expect(seed().value).toBe('9');
    expect(input.value).toBe('');
    expect(status()).toContain('Scenario loaded');
    expect(post).not.toHaveBeenCalled();
  });

  it.each(['oversized', 'unreadable'])(
    'reports an %s file without replacing the old run',
    async (kind) => {
      await mount();
      const file = new File([kind === 'oversized' ? 'x'.repeat(65537) : '{}'], 'request.json');
      Object.defineProperty(file, 'text', {
        value: async () => {
          throw new Error('Read failed');
        },
      });
      const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
      Object.defineProperty(input, 'files', { configurable: true, value: [file] });
      await act(async () => input.dispatchEvent(new Event('change', { bubbles: true })));
      expect(container.querySelector('[role="alert"]')!.textContent).toContain(
        kind === 'oversized' ? '64 KB' : 'could not be read',
      );
      expect(status()).toContain('Saved run displayed');
    },
  );

  it('blocks invalid draft exports while retaining the exact completed-request download', async () => {
    await mount();
    await type(seed(), 'invalid');
    expect(button('Save current request').disabled).toBe(true);
    await click(button('Save current request'));
    expect(downloads).toHaveLength(0);
    await click(button('Save request', container.querySelector('.run-receipt')!));
    expect(await exported()).toEqual(exampleRequest);
  });

  it('shows explicit sample-unavailable text when the request omits a sample match', async () => {
    const request = { ...exampleRequest, include_sample_match: false };
    const result = copy(savedRun.response);
    result.data.sample_match = null;
    post.mockResolvedValue(response(result));
    await mount();
    await type(json(), JSON.stringify(request));
    await click(button('Load request'));
    await click(button('Run simulation'));
    expect(status()).toContain('New run complete');
    expect(container.querySelector('.sample-timeline')).toBeNull();
    expect(container.querySelector('.sample-scorecard')!.textContent).toContain(
      'did not request a sample',
    );
  });

  it('rejects future evidence in an archive replay and does not run under an open facts dialog', async () => {
    const match = {
      ...snapshots[2026].matches[0],
      team1_id: 'CSK',
      team2_id: 'MI',
      venue_id: exampleRequest.venue_id,
      match_date: '2026-04-01',
    };
    await mount({ example: false, match });
    await act(async () =>
      document.body.dispatchEvent(
        new KeyboardEvent('keydown', { code: 'Space', bubbles: true, cancelable: true }),
      ),
    );
    expect(post).not.toHaveBeenCalled();
    await click(container.querySelector<HTMLButtonElement>('[aria-label="Close match record"]')!);
    await type(json(), JSON.stringify(exampleRequest));
    await click(button('Load request'));
    expect(container.querySelector('[role="alert"]')!.textContent).toContain('cutoff');
    expect(container.querySelector('.verdict-board')).toBeNull();
  });

  it('focuses Run setup and invokes the theme and return actions', async () => {
    const onBack = vi.fn(),
      onTheme = vi.fn();
    await mount({ onBack, onTheme });
    await click(button('Run setup'));
    expect(document.activeElement).toBe(container.querySelector('#run-controls'));
    await click(container.querySelector<HTMLButtonElement>('[aria-label="Switch to dark mode"]')!);
    await click(button('Fixtures', container.querySelector('.platform-wayfinding')!));
    expect(onTheme).toHaveBeenCalledTimes(1);
    expect(onBack).toHaveBeenCalledTimes(1);
  });

  it('exports the current draft separately from the immutable completed request and full receipt', async () => {
    await mount();
    await type(seed(), '0');
    await click(button('50'));
    await click(button('Save current request'));
    expect(await exported()).toEqual({ ...exampleRequest, seed: 0, simulations: 50 });
    await click(button('Save request', container.querySelector('.run-receipt')!));
    expect(await exported()).toEqual(exampleRequest);
    await click(button('Save full run'));
    expect(await exported()).toEqual({
      request: savedRun.request,
      response: savedRun.response,
      source: 'saved',
      completed_at: null,
    });
  });

  it('transfers the draft and its older completed run to Lab without pretending they match', async () => {
    const edit = vi.fn();
    await mount({ onEditLab: edit });
    await type(seed(), '0');
    await click(button('Edit team plans in Lab'));
    expect(edit.mock.calls[0][0].seed).toBe(0);
    expect(edit.mock.calls[0][1].request.seed).toBe(exampleRequest.seed);
  });

  it('publishes a completed Lab scenario once and shows the supplied names', async () => {
    const publish = vi.fn();
    await mount({
      example: false,
      scenario: {
        request: exampleRequest,
        run: null,
        toss: { winnerId: 'CSK', decision: 'bat' },
        names: { [exampleRequest.team_a.batting_order[0]]: 'Scenario opener' },
        venueName: 'Test ground',
      },
      scenarioLabel: 'Lab scenario A',
      onScenarioRun: publish,
    });
    expect(container.textContent).toContain('Scenario opener');
    await click(button('Run simulation'));
    expect(publish).toHaveBeenCalledTimes(1);
    expect(publish.mock.calls[0][0].request).toEqual(exampleRequest);
  });

  it('disables 2025 replay imports', async () => {
    await mount({ example: false, match: snapshots[2025].matches[0] });
    await click(container.querySelector<HTMLButtonElement>('[aria-label="Close match record"]')!);
    expect(json().disabled).toBe(true);
    expect(button('Choose request file').disabled).toBe(true);
    expect(container.textContent).toContain('Simulation profile unavailable for 2025');
  });

  it('shows expired-session recovery and invokes the return action', async () => {
    const back = vi.fn();
    await mount({ example: false, expiredScenario: true, onBack: back, backLabel: 'Lab' });
    expect(container.textContent).toContain('Scenario session ended');
    await click(button('Back to Lab'));
    expect(back).toHaveBeenCalledTimes(1);
  });

  it('switches both supplied XIs and batting/bowling scorecards without changing win estimates', async () => {
    await mount();
    const odds = container.querySelector('.verdict-board')!.textContent;
    const supplied = container.querySelector('.supplied-plans')!;
    await click(button('MI', supplied));
    expect(supplied.querySelector('.plan-order')!.textContent).toContain(
      savedScenario.players[
        exampleRequest.team_b.batting_order[0] as keyof typeof savedScenario.players
      ],
    );
    const card = container.querySelector('.sample-scorecard')!;
    await click(button('MI innings', card));
    await click(button('Bowling', card));
    expect(card.querySelector('thead')!.textContent).toContain('Econ');
    expect(card.querySelectorAll('tbody tr')).toHaveLength(
      savedRun.response.data.sample_match!.innings[1].bowling.length,
    );
    await click(button('Batting', card));
    const batting = savedRun.response.data.sample_match!.innings[1].batting;
    for (const [index, player] of batting.entries()) {
      if (!player.entered)
        expect(card.querySelectorAll('tbody tr')[index].textContent).toContain('DNB———');
    }
    expect(container.querySelector('.verdict-board')!.textContent).toBe(odds);
  });
});

describe('Phase 2: sample over navigation', () => {
  it('shows the final chase event when a wide wins immediately after a completed over', async () => {
    const innings = copy(savedRun.response.data.sample_match!.innings);
    const event = innings[1].deliveries![0];
    innings[1] = {
      ...innings[1],
      runs: 11,
      wickets: event.wickets,
      legal_balls: 6,
      deliveries: [
        { ...event, physical_delivery: 1, legal_balls_before: 5, kind: 'legal', score: 10 },
        {
          ...event,
          physical_delivery: 2,
          legal_balls_before: 6,
          kind: 'wide',
          score: 11,
          extras: 1,
        },
      ],
    };
    await act(async () => root.render(<OverLine innings={innings} names={{}} />));
    await click(button('Mumbai'));
    const station = container.querySelector<HTMLButtonElement>('[aria-label^="Over 2"]')!;
    expect(station.disabled).toBe(false);
    await click(station);
    expect(container.querySelector('.sample-current-score')!.textContent).toBe(
      `11/${innings[1].wickets}`,
    );
    expect(container.querySelector('.delivery-cells')!.textContent).toBe('1wd');
    expect(container.querySelector('.sample-position')!.textContent).toContain('After 1.0 overs');
    expect(station.getAttribute('aria-label')).toContain('innings ends at 1.0');
  });

  it('scrubs with arrows, clamps to the last available over, and resets when changing innings', async () => {
    await mount();
    const timeline = container.querySelector('.sample-timeline')!;
    const first =
      timeline.querySelector<HTMLButtonElement>('[aria-label^="Over 1,"]') ||
      timeline.querySelector<HTMLButtonElement>('[aria-label="Over 1"]')!;
    await act(async () =>
      first.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true }),
      ),
    );
    expect(timeline.querySelector('[aria-pressed="true"].over-station')!.textContent).toBe('2');
    expect(document.activeElement).toBe(
      timeline.querySelector('[aria-pressed="true"].over-station'),
    );
    await click(button('Mumbai', timeline));
    expect(timeline.querySelector('[aria-pressed="true"].over-station')!.textContent).toBe('1');
  });
});
