# The Concourse — completed frontend

A local React + TypeScript interface for the existing IPL archive and simulator. All five frontend phases are complete: Fixtures, Match, Lab, Record and final integration/polish. The interface provides recorded match facts, experimental simulations, team-plan/XI optimization and separate research evidence in both themes. See the [completed frontend guide](../docs/frontend-release.md) for startup, verification, review images and scope, plus the detailed [Match](../docs/frontend-match.md), [Lab](../docs/frontend-lab.md) and [Record](../docs/frontend-record.md) guides. Model accuracy and validation remain unchanged.

From the project root, run `./scripts/start_frontend.ps1`, then open http://127.0.0.1:5173. Dependencies are already installed in this workspace. For a fresh checkout:

```powershell
cd frontend
npm ci
npm run dev
```

Node 24 is used locally. The lockfile pins dependency resolution. Fonts are bundled locally; there is no runtime font CDN, analytics, hosted service, external image request or chart-library dependency. Font copyright and SIL Open Font License notices are retained under `public/licenses/` and copied into the production build.

## Data connection

The interface displays the saved 2025 or 2026 project archive immediately, then checks the backend. Start `./scripts/start_backend.ps1` in a separate terminal for the API. Vite forwards `/api` to `http://127.0.0.1:8000` in development. Copy `.env.example` to `.env.local` only if a different API base is needed, then restart Vite.

- `GET /api/v1/matches?season=2026&limit=100&offset=0`: complete selected-season archive. Responses from another season, partial pages or unsupported shapes fall back to the saved snapshot.
- `GET /api/v1/matches/{id}`: recorded innings for the pinned and selected match. If an API detail fails, its score is marked unavailable rather than silently replacing it with a score from another source.
- `POST /api/v1/simulations/match`: explicit 2026 planning scenarios, 50–1,000 trials. Completed results retain their submitted inputs. A saved CSK/MI run is labelled separately and is never silently substituted for a failed live run.
- `GET /api/v1/teams/{id}/roster?season=2026`: selected roster proxies, with explicit saved/API labels. Lab bundles ten public roster extracts and 37 grounds.
- `POST /api/v1/optimization/xi`: up to three constrained candidates with 50–500 trials and independent selected-candidate confirmation. Saved optimizer output is labelled separately; failed computations never fabricate a candidate. Applying a plan requires a new simulation to update its odds.
- The visible source strip distinguishes **Local archive API** from **Saved archive snapshot**. The source is not a live-score status. Connection checks are bounded at three seconds and can be retried.
- Record uses a separately labelled saved research extract and needs no backend connection. It never recalculates a historical forecast using current plans or current rosters. Its export/source hashes are described in the [Record guide](../docs/frontend-record.md).

Snapshots include 74 records for each season and the associated innings. They are derived from the existing `outputs/ipl-data/ipl.sqlite`, not a freshly verified official schedule. Display aliases use current team names without changing historical database identity. There are no invented kickoff times, schedules, venue conditions, forecasts or historical prediction probabilities.

To refresh these public-data extracts, run from the project root:

```powershell
.venv/Scripts/python.exe scripts/export_frontend_archive.py
```

The export opens SQLite read-only and verifies its SHA-256 has not changed. Each extract stores that source hash and export time. It includes explicit match and innings fields, excluding raw source pages and player/private metadata. Distribution of third-party dataset derivatives still follows the existing project's redistribution review.

## Controls

- Season, match-category, team and ground filters combine. The free-text board filter searches team names, venue, city, date, reference and stage. Reset restores the current season's complete board.
- The URL retains season, team, ground, category and selected match. Free-text board search is transient.
- Select a team in the right-hand line key to filter. On mobile, use the Team toggle.
- Press `/` or Ctrl/Cmd+K for the archive command kiosk. Search a team, ground, date or reference; use arrows and Enter to select, Escape to close.
- Up/down arrows on match buttons move between visible records. `1` returns to Fixtures; `2` opens Match or the active Lab scenario; `3` opens Lab; `4` opens Record. Space runs a supplied Match scenario outside inputs/buttons. Left/right arrows move through sample overs.
- Lab drafts and results survive navigation within the page session and reset on reload. Copying A/B transfers inputs and clears the destination result. A/B deltas require fresh outputs and matching trial count, seed, evidence cutoff, dataset and model versions. Changing or applying plans keeps older outputs visibly stale until a successful run.
- Save requests before reloading. A reloaded temporary Lab scenario explains that its session ended and returns to Lab. Workspace changes start at the top; dialogs return focus to the initiating control on close.
- Theme choice persists locally. Native dialogs contain focus and support Escape. The board has a skip link and visible keyboard focus states. Flap movement respects reduced-motion preferences. No animation manufactures simulation progress.

## Checks and production preview

```powershell
npm test
npm run build
npm run format:check
npm run preview
```

The production preview intentionally has no backend proxy and uses labelled snapshots. For a deployed build to use the backend, serve `/api` through an appropriate reverse proxy or configure `VITE_API_BASE_URL` before building and allow the frontend origin in backend CORS. This phase does not deploy the application or expose the local backend publicly.

The 86 tests cover archive segregation, filters, routes, snapshots, team-bullet AA contrast, simulation/optimizer response integrity, plan constraints, Impact semantics, request correspondence, comparison freshness, research artifact hashes, cohort/calibration accounting, honest target/baseline interpretation and error handling. Manual checks and screenshots are recorded in [the phase plan](../docs/frontend-phases.md) and the workspace guides.
