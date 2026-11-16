import { afterEach, describe, expect, it, vi } from 'vitest';
import { liveAdapter, snapshots } from './client';

afterEach(() => vi.unstubAllGlobals());
function response(data: unknown, ok = true) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({ ok, status: ok ? 200 : 503, json: async () => data }),
  );
}
describe('archive API boundary', () => {
  const match = snapshots[2026].matches[0];
  it('normalizes the API season field and passes cancellation through', async () => {
    response({ items: [{ ...match, season: '2026' }], total: 1, offset: 0 });
    const signal = new AbortController().signal;
    const rows = await liveAdapter.getMatches(2026, signal);
    expect(rows[0].season).toBe(2026);
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('season=2026'),
      expect.objectContaining({ signal }),
    );
  });
  it('rejects a partial page rather than showing a misleading record count', async () => {
    response({ items: [match], total: 74, offset: 0 });
    await expect(liveAdapter.getMatches(2026)).rejects.toThrow('incomplete');
  });
  it('rejects cross-season and malformed responses', async () => {
    response({ items: [match], total: 1, offset: 0 });
    await expect(liveAdapter.getMatches(2025)).rejects.toThrow('contract');
    response({ items: [{ match_id: 'x' }], total: 1, offset: 0 });
    await expect(liveAdapter.getMatches(2026)).rejects.toThrow('contract');
  });
  it('rejects HTTP errors for the caller to use its labelled snapshot', async () => {
    response({}, false);
    await expect(liveAdapter.getMatches(2026)).rejects.toThrow('503');
  });
  it('checks that detail innings belong to the requested match', async () => {
    response({
      data: { match, innings: [{ ...snapshots[2026].innings[0], match_id: 'wrong-id' }] },
    });
    await expect(liveAdapter.getInnings(match.match_id)).rejects.toThrow('incomplete');
  });
});
