// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import { PlanningProvider } from './PlanningContext';
import { snapshots } from './api/client';
import { savedRosters } from './api/lab';

let root: Root;
let container: HTMLDivElement;

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
  vi.stubGlobal('scrollTo', vi.fn());
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
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
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => {
      const url = new URL(input, window.location.origin);
      const season = url.searchParams.get('season') === '2025' ? 2025 : 2026;
      const archive = snapshots[season];
      let body: unknown;
      if (url.pathname.endsWith('/matches')) {
        body = { items: archive.matches, total: archive.matches.length, offset: 0, limit: 100 };
      } else if (url.pathname.includes('/matches/')) {
        const id = url.pathname.split('/').at(-1);
        const match = [...snapshots[2025].matches, ...snapshots[2026].matches].find(
          (row) => row.match_id === id,
        );
        body = {
          data: {
            match,
            innings: [...snapshots[2025].innings, ...snapshots[2026].innings].filter(
              (row) => row.match_id === id,
            ),
          },
        };
      } else if (url.pathname.includes('/roster')) {
        const id = url.pathname.split('/').at(-2)!;
        body = { data: savedRosters[id] };
      } else throw new Error(`Unexpected request in foundation test: ${url.pathname}`);
      return { ok: true, status: 200, json: async () => body };
    }),
  );
  window.history.replaceState(null, '', '#/fixtures?season=2026');
  window.localStorage.clear();
  document.documentElement.dataset.theme = 'light';
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

async function settle() {
  await act(async () => {
    await new Promise((resolve) => window.setTimeout(resolve, 0));
    await vi.dynamicImportSettled();
  });
}
async function mount(hash?: string) {
  if (hash) window.history.replaceState(null, '', hash);
  await act(async () =>
    root.render(
      <PlanningProvider>
        <App />
      </PlanningProvider>,
    ),
  );
  await settle();
}
function button(text: string, scope: ParentNode = container) {
  const match = [...scope.querySelectorAll<HTMLButtonElement>('button')].find((node) =>
    node.textContent?.replace(/\s+/g, ' ').trim().includes(text),
  );
  if (!match) throw new Error(`Button missing: ${text}`);
  return match;
}
async function click(node: HTMLElement) {
  await act(async () => node.click());
  await settle();
}
async function type(input: HTMLInputElement, value: string) {
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await settle();
}
async function key(key: string, target: HTMLElement = document.body, ctrlKey = false) {
  await act(async () => {
    target.dispatchEvent(
      new KeyboardEvent('keydown', { key, ctrlKey, bubbles: true, cancelable: true }),
    );
  });
  await settle();
}
const count = () => Number(container.querySelector('.header-count strong')?.textContent);
const boardInput = () =>
  container.querySelector<HTMLInputElement>('[aria-label="Filter the board"]')!;
const commandInput = () =>
  container.querySelector<HTMLInputElement>('[aria-label="Search archive commands"]')!;

describe('Phase 1: Fixtures and shared navigation interactions', () => {
  it('connects the archive and paginates all 74 unique rows to the end', async () => {
    await mount();
    expect(container.querySelector('.source-label')?.textContent).toContain('API');
    expect(count()).toBe(74);
    expect(container.querySelectorAll('.match-row')).toHaveLength(12);
    for (const expected of [24, 36, 48, 60, 72, 74]) {
      await click(button('Show '));
      expect(container.querySelectorAll('.match-row')).toHaveLength(expected);
    }
    const references = [...container.querySelectorAll('.match-row .reference .mono')].map(
      (n) => n.textContent,
    );
    expect(new Set(references).size).toBe(74);
    expect(container.querySelector('.board-bottom')?.textContent).toContain('End of selection');
  });

  it('switches seasons and categories without carrying old filters into the new season', async () => {
    await mount();
    await click(button('Playoffs'));
    expect(count()).toBe(4);
    await click(button('League', container.querySelector('.filter-panel')!));
    expect(count()).toBe(70);
    await click(button('No result', container.querySelector('.filter-panel')!));
    expect(count()).toBe(2);
    await click(button('2025', container.querySelector('.filter-panel')!));
    expect(count()).toBe(74);
    expect(window.location.hash).toBe('#/fixtures?season=2025');
    await click(button('No result', container.querySelector('.filter-panel')!));
    expect(count()).toBe(4);
  });

  it('combines team, ground, category and text filters, then resets everything', async () => {
    await mount('#/fixtures?season=2026&team=RCB&venue=venue_fb4f23161a&stage=playoffs');
    expect(count()).toBe(1);
    await type(boardInput(), '1535465');
    expect(count()).toBe(1);
    await type(boardInput(), 'does-not-exist-987');
    expect(count()).toBe(0);
    expect(container.querySelector('.empty-state h2')?.textContent).toContain('No matches');
    await click(button('Clear filters'));
    expect(count()).toBe(74);
    expect(boardInput().value).toBe('');
    expect(window.location.hash).toBe('#/fixtures?season=2026');
  });

  it('searches case-insensitive cities and references and clears the query', async () => {
    await mount();
    await type(boardInput(), '  aHMeDabad  ');
    expect(count()).toBe(8);
    await type(boardInput(), '1535465');
    expect(count()).toBe(1);
    await click(container.querySelector<HTMLButtonElement>('[aria-label="Clear board search"]')!);
    expect(count()).toBe(74);
  });

  it('opens row facts directly and Back to fixtures preserves the filter context', async () => {
    await mount('#/fixtures?season=2026&team=RCB&stage=playoffs');
    await click(container.querySelector<HTMLButtonElement>('.match-link')!);
    expect(container.querySelector('dialog[open]')?.textContent).toContain('1535465');
    expect(container.querySelector('dialog[open]')?.textContent).toContain('161/5');
    await click(button('Back to fixtures', container.querySelector('dialog')!));
    expect(window.location.hash).toBe('#/fixtures?season=2026&team=RCB&stage=playoffs');
    expect(count()).toBe(2);
  });

  it('moves focus through board rows with ArrowDown and wraps with ArrowUp', async () => {
    await mount();
    const rows = [...container.querySelectorAll<HTMLButtonElement>('.match-link')];
    rows[0].focus();
    await key('ArrowDown', rows[0]);
    expect(document.activeElement).toBe(rows[1]);
    await key('ArrowUp', rows[1]);
    expect(document.activeElement).toBe(rows[0]);
    await key('ArrowUp', rows[0]);
    expect(document.activeElement).toBe(rows.at(-1));
  });

  it('launches command search from its button, slash and Control K', async () => {
    await mount();
    const launch = container.querySelector<HTMLButtonElement>(
      '[aria-label="Find a record, slash shortcut"]',
    )!;
    launch.focus();
    await click(launch);
    expect(document.activeElement).toBe(commandInput());
    await click(container.querySelector<HTMLButtonElement>('[aria-label="Close search"]')!);
    expect(document.activeElement).toBe(launch);
    await key('/');
    expect(container.querySelector('dialog[open]')).not.toBeNull();
    await key('k', commandInput(), true);
    expect(container.querySelector('dialog')).toBeNull();
    await key('k', boardInput(), true);
    expect(container.querySelector('dialog[open]')).not.toBeNull();
  });

  it('selects a team through keyboard command search and clears conflicting filters', async () => {
    await mount('#/fixtures?season=2026&venue=venue_fb4f23161a&stage=playoffs');
    await key('/');
    await type(commandInput(), 'CSK');
    await key('Enter', commandInput());
    expect(container.querySelector('dialog')).toBeNull();
    expect(window.location.hash).toBe('#/fixtures?season=2026&team=CSK');
    expect(count()).toBe(14);
  });

  it('finds a ground and opens a match reference through command search', async () => {
    await mount();
    await key('/');
    await type(commandInput(), 'Narendra Modi');
    await key('Enter', commandInput());
    expect(count()).toBe(8);
    expect(window.location.hash).toContain('venue=venue_fb4f23161a');
    await key('/');
    await type(commandInput(), '1535465');
    await key('Enter', commandInput());
    expect(container.querySelector('.record-dialog[open]')?.textContent).toContain('155/8');
  });

  it('keeps empty command results safe, navigates options and handles native cancellation', async () => {
    await mount();
    await key('/');
    await key('ArrowDown', commandInput());
    expect(commandInput().getAttribute('aria-activedescendant')).toBe('command-1');
    await key('ArrowUp', commandInput());
    expect(commandInput().getAttribute('aria-activedescendant')).toBe('command-0');
    await type(commandInput(), 'does-not-exist-987');
    await key('Enter', commandInput());
    expect(container.querySelector('.command-empty')?.textContent).toContain('No matching records');
    expect(commandInput().hasAttribute('aria-activedescendant')).toBe(false);
    await act(async () =>
      container.querySelector('dialog')!.dispatchEvent(new Event('cancel', { cancelable: true })),
    );
    expect(container.querySelector('dialog')).toBeNull();
  });

  it('closes command search when the backdrop is clicked', async () => {
    await mount();
    await key('/');
    await click(container.querySelector('dialog')!);
    expect(container.querySelector('dialog')).toBeNull();
  });

  it('routes keyboard shortcuts to all workspaces but ignores them while typing', async () => {
    await mount();
    await key('3', boardInput());
    expect(window.location.hash).toBe('#/fixtures?season=2026');
    for (const [shortcut, prefix, title] of [
      ['2', '#/match/', 'Scenario'],
      ['3', '#/lab', 'Lab'],
      ['4', '#/record', 'Record'],
      ['1', '#/fixtures', 'Fixtures'],
    ]) {
      await key(shortcut);
      expect(window.location.hash.startsWith(prefix)).toBe(true);
      expect(document.title).toContain(title);
      expect(container.querySelector('[aria-current="page"]')?.textContent).toContain(shortcut);
    }
  });

  it('supports navigation buttons and skip links in every workspace', async () => {
    await mount();
    for (const [name, target] of [
      ['Lab', 'lab-content'],
      ['Record', 'record-content'],
      ['Match', 'match-content'],
      ['Fixtures', 'board-content'],
    ]) {
      await click(button(name, container.querySelector('.places')!));
      await click(container.querySelector<HTMLAnchorElement>('.skip-link')!);
      expect(document.activeElement?.id).toBe(target);
    }
  });

  it('shares light/dark state across navigation and saves the chosen preference', async () => {
    await mount();
    await click(container.querySelector<HTMLButtonElement>('[aria-label="Switch to dark mode"]')!);
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(localStorage.getItem('concourse-theme')).toBe('dark');
    await key('3');
    expect(container.querySelector('[aria-label="Switch to light mode"]')).not.toBeNull();
    await click(container.querySelector<HTMLButtonElement>('[aria-label="Switch to light mode"]')!);
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(localStorage.getItem('concourse-theme')).toBe('light');
  });

  it('recovers from unsupported routes and unknown record references', async () => {
    await mount('#/unexpected?season=1900&stage=unknown');
    expect(count()).toBe(74);
    await act(async () => {
      window.location.hash = '#/match/not-a-record?season=2026';
    });
    await settle();
    expect(container.textContent).toContain('Record not found');
    await click(button('Back to Fixtures'));
    expect(container.querySelector('h1')?.textContent).toContain('Fixtures');
  });
});
