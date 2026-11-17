// @vitest-environment jsdom
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { snapshots } from '../api/client';
import type { ArchiveMatch } from '../api/contracts';
import MatchWorkspace from './MatchWorkspace';

let root: Root;
let container: HTMLDivElement;
let back = vi.fn<() => void>();

beforeEach(() => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({ matches: true }));
  // jsdom has no native top layer. Keep these stubs limited to dialog lifecycle,
  // while the live-browser checks verify native modal focus and dismissal.
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
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  back = vi.fn<() => void>();
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

async function renderRecord(match: ArchiveMatch | undefined = snapshots[2026].matches[0]) {
  await act(async () => {
    root.render(
      <MatchWorkspace
        match={match}
        example={false}
        missing={false}
        source="snapshot"
        onBack={back}
        onExample={vi.fn()}
        theme="light"
        onTheme={vi.fn()}
      />,
    );
  });
}

describe('opening a recorded fixture', () => {
  it('shows the recorded score immediately, without a second click or a simulation', async () => {
    await renderRecord();
    const dialog = container.querySelector('dialog[open]');
    expect(dialog).not.toBeNull();
    expect(dialog!.textContent).toContain('155/8');
    expect(dialog!.textContent).toContain('161/5');
    expect(dialog!.textContent).toContain('1535465');
    expect(dialog!.textContent).toContain('Saved archive snapshot');
    expect(dialog!.textContent).toContain('does not contain a pre-match prediction');
  });

  it('Back to fixtures invokes navigation rather than only hiding the facts', async () => {
    await renderRecord();
    const button = [...container.querySelectorAll<HTMLButtonElement>('dialog button')].find((node) =>
      node.textContent?.includes('Back to fixtures'),
    )!;
    await act(async () => button.click());
    expect(back).toHaveBeenCalledTimes(1);
  });

  it('dismisses and reopens facts while preserving the explicit replay workspace', async () => {
    await renderRecord();
    await act(async () => {
      container.querySelector<HTMLButtonElement>('[aria-label="Close match record"]')!.click();
    });
    expect(container.querySelector('dialog')).toBeNull();
    expect(back).not.toHaveBeenCalled();
    const reopen = [...container.querySelectorAll('button')].find((node) =>
      node.textContent?.includes('View recorded result'),
    )!;
    await act(async () => reopen.click());
    expect(container.querySelector('dialog[open]')).not.toBeNull();
  });

  it('also opens facts when archive data becomes available after the route mounts', async () => {
    // Pass a missing record explicitly so the default fixture is not selected.
    await act(async () => {
      root.render(
        <MatchWorkspace
          example={false}
          missing={false}
          source="snapshot"
          onBack={back}
          onExample={vi.fn()}
          theme="light"
          onTheme={vi.fn()}
        />,
      );
    });
    expect(container.querySelector('dialog')).toBeNull();
    await renderRecord();
    expect(container.querySelector('dialog[open]')?.textContent).toContain('1535465');
  });

  it('preserves a no-result record without inventing a winner', async () => {
    const abandoned = snapshots[2025].matches.find((match) => !match.winner_id)!;
    await renderRecord(abandoned);
    const dialog = container.querySelector('dialog[open]')!;
    expect(dialog.textContent).toContain('No result recorded');
    expect(dialog.textContent).toContain(abandoned.match_id);
  });
});
