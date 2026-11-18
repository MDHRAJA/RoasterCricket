# The Concourse — Match workspace

Phase 2 adds the Match interface to the existing local project. It does not alter the simulator, promote a research model or change measured prediction accuracy. Phase 3 connects the [Lab plan editor](frontend-lab.md); Phase 4 presents the separate saved [Record evidence](frontend-record.md).

## Open it

From the project root, use two terminals:

```powershell
.\scripts\start_backend.ps1
```

```powershell
.\scripts\start_frontend.ps1
```

Open http://127.0.0.1:5173/#/match/scenario-csk-mi?season=2026 or choose **Match** in the numbered navigation. Fixtures also has a **CSK v MI simulation** entry. The saved example remains reviewable while Python is stopped; its source is explicitly labelled **Saved output**.

## What is displayed

- **Win estimate:** outcome counts, unconditional team win shares, unresolved-tie share and 95% Wilson sampling intervals returned by the backend. The interval is finite-trial sampling error, not total uncertainty or historical prediction accuracy. Super Over occurrence is displayed separately and is not added to outcome shares.
- **Innings totals:** 10-run histograms on a shared run axis, mean runs, median and the middle 80% of modeled totals. Missing histogram positions are empty zero-count bins, not invented observations. Chase totals can end at the target, so they are not an unconstrained comparison of batting strength. Exact counts can be opened as a table.
- **Run receipt:** exclusive evidence cutoff, last training match, recorded delivery count, trial count, seed, result source, availability assumption, eligibility status, model variant and sampled-exposure support. Full assumptions are available in a disclosure. The model remains experimental and not match-level calibrated.
- **Supplied XI:** the submitted batting order, captain and 20-over bowling schedule. These are inputs to this run. They are not an optimized XI or an assessment of captaincy.
- **One simulated innings:** a 20-station sample OverLine shows the backend's first-trial trace. Left/right arrows move between available overs. Wicket stations have a second ring and a textual label; wides and no-balls stay in their legal-ball over. Unreached overs are disabled when a chase/all-out ends early. Only the sample score and delivery cells change; the full-run pre-match odds remain fixed.
- **Sample scorecard:** final batting or bowling figures for either innings of that one trial. DNB is displayed as DNB with missing figures, rather than zero runs. These are not player projections or fantasy forecasts.

There are no invented per-trial score arrays, ball-probability matrices, evolving win curves, shot directions, streaming progress counts or projected player ranges. The API does not return those aggregate fields.

## New runs and failures

Choose 50, 200, 500 or 1,000 trials and a seed. Imported requests can also specify intermediate integer trial counts. The backend accepts 50–1,000. Seed zero is valid. The unknown-availability checkbox is an explicit planning assumption, not confirmation that a player is fit or available. Unticking it lets the backend enforce its dated-availability checks.

Press **Run simulation**, or Space outside an input/control. A run posts the complete normalized request to `/api/v1/simulations/match`. The service returns one complete result, so the interface shows a waiting state without fabricated partial counts. Trial and seed controls are locked while waiting.

Every displayed result stays paired with the exact request that generated it. Editing settings marks **Inputs changed** and leaves the previous odds intact until a new run succeeds. HTTP 422 rule failures, 429 occupied-slot responses, connection errors and incompatible responses are shown as failures, not converted into forecasts or silently replaced by the saved example. The previous completed run remains available if one exists.

**Stop waiting** aborts the browser request and ignores late responses. It does not kill Python's computation. The backend may finish its existing job and return 429 to a second request meanwhile. Leaving the workspace also aborts the browser wait. The browser timeout is 45 seconds; the backend maintains its own computation budget.

The seed repeated identical win estimates in the current local runtime during browser QA. Reproducibility also depends on the dataset, full request, code and numerical-library versions. **Save current request** exports the current draft, including edited trials, seed and availability. Invalid seeds disable that draft export. The receipt's **Save request** and **Save full run** retain the exact completed inputs and outputs even when the draft has changed. Standalone imported requests and results reset when Match is left/reloaded. Lab scenarios retain drafts and completed runs across navigation within the page session, then reset on reload. **Edit team plans in Lab** explicitly transfers the current Match draft to a scenario slot.

## Archive replay and request import

Selecting an archived match opens its observed score/result dialog immediately. Dismissing it reveals the replay workspace; **View recorded result** reopens the facts. **Back to fixtures** navigates to Fixtures. No simulated forecast is automatically inferred from that result or from a broad participant pool.

To simulate an archive pairing, expand **Load an explicit scenario request**. Import a JSON file (up to 64 KB), or paste the request. It must include both starting XIs, batting orders, twenty bowling assignments, captains, venue, cutoff and batting-first team. Client checks validate structure; the backend remains authoritative for roster and rule constraints. For an archive replay, teams and venue must match the selected record, the cutoff must be on/before the match date, and the rule season must be 2026. Even then, the result is a hypothetical replay, not a recovered historical forecast or a verified historical lineup.

The example uses the existing `outputs/match-simulation-request.json` and `outputs/match-simulation-example.json`. Its XIs are an arbitrary role-balanced planning baseline, not a match-ready recommendation. The bundled response is real saved simulator output. `scripts/export_frontend_scenario.py` validates the paired request/response identifiers and exports public player names from SQLite read-only. Source filenames and SHA-256 values are retained under `provenance` in the bundled extract. Regenerate it from the project root with:

```powershell
.venv\Scripts\python.exe -m scripts.export_frontend_scenario
```

## Checks

From `frontend/`:

```powershell
npm test
npm run build
npm run format:check
```

The Phase 2 checkpoint had 46 tests. Added coverage included bounded requests, seed zero, request/result correspondence, preserved tie mass, histogram reconciliation, invalid responses, backend errors, illegal deliveries, early sample endings and archive-context restrictions. Manual browser checks included live runs, repeatability, cancellation, request import, details, keyboard controls and mobile geometry. The downloaded saved-run export retained its 200-trial request, response, seed and saved source. A final check with the owned backend stopped showed a connection failure while retaining the prior saved result. Review images are under `docs/frontend-review/`; `phase2-match-light.jpg` and `phase2-match-dark.jpg` show a live 200-trial API result, while the mobile/overview images show the separately labelled saved example. The saved SQLite SHA-256 still matches the Phase 1 extract. See the phase plan for subsequent suite totals.

The Match chunk is loaded only when opened, preserving the Fixtures entry path. Fonts are local and no new runtime library was added for this phase. The interface has reduced-motion styles, chart text alternatives, exact data tables, keyboard focus and native dialogs. Further cross-browser and assistive-technology review belongs to the final integration phase.

## Repeatable live-service checks

The normal suite mocks network boundaries. Four optional live checks send five sequential simulation requests: a repeated 50-trial seed-zero run, reversed batting order without a sample, the 200-trial example, and strict availability rejection. They validate real responses through the same frontend boundary as Match. Run from `frontend/` against the intended backend:

```powershell
$env:VITE_API_BASE_URL = 'https://roaster-cricket-api.vercel.app/api/v1'
$env:VITE_LIVE_MATCH_QA = '1'
npm test -- src/api/simulation.live.test.ts
Remove-Item Env:VITE_LIVE_MATCH_QA
Remove-Item Env:VITE_API_BASE_URL
```

These consume computation on the selected service and are skipped by default. They do not exercise browser layout or establish prediction accuracy. The current regression pass is recorded in [bug testing](bug-testing.md).
