# The Concourse — Lab workspace

Phase 3 connects manual team planning, two scenario slots and the existing XI optimizer. It changes no prediction model, calibration, historical accuracy or database contents. Phase 4 now presents the separate saved [Record evidence](frontend-record.md).

## Open it

From the project root, start these in separate terminals:

```powershell
.\scripts\start_backend.ps1
```

```powershell
.\scripts\start_frontend.ps1
```

Open http://127.0.0.1:5173/#/lab?season=2026, choose **Lab**, or press **3** outside an input. Planning uses the backend's 2026 rules. Fixtures from 2025 remain an archive, not an enabled 2025 planning service.

## Inputs and results

Slots **A** and **B** hold separate requests and completed simulation results. Copy transfers inputs and clears the destination result. Drafts and completed optimizer results survive navigation between Lab and Match within this page session; reloading resets them. Theme preference persists separately.

Choose either franchise from ten public roster proxies, one of 37 recorded grounds, an exclusive evidence cutoff, seed and trial count. A hypothetical toss winner and bat/field choice determine who bats first. Only that effective batting-first order enters the model; winning the toss itself adds no learned effect. The unknown-availability checkbox explicitly allows unknown dated availability. It never confirms fitness or match-day eligibility.

The editor supports eleven starters, captain nomination, batting order, twenty bowling assignments, up to five nominated substitutes and one explicit domestic interval Impact replacement. Move batting positions with the arrow buttons or drag a strip. Removing a player clears their bowling assignments, leaving visible gaps to repair. Each over selector restricts assignments to active fielders, at most four overs per bowler and no consecutive overs. A manual plan permits any active fielder; the optimizer uses the narrower recorded bowler/all-rounder role pool. Captain nomination has no modeled captaincy effect.

For an Impact plan, nominate the incoming domestic substitute, then explicitly choose the outgoing and incoming players. The replacement occurs only between innings. Batting order and bowling availability follow the active XI for that innings. Overseas replacements, mid-innings substitutions and the complete supplementary Impact eligibility rules are outside this implementation. Switching batting-first order reconciles affected positions and leaves invalid bowling assignments visibly unassigned.

Client checks identify roster membership, XI/substitute conflicts, keeper coverage, country-based overseas proxy, dated availability, batting order and bowling constraints. Unknown overseas classifications are not treated as domestic. The API rechecks the full request. Public roster membership and profile labels are separate from verified match-day eligibility.

**Run scenario** submits the exact draft to `/api/v1/simulations/match`. **Open in Match** carries the plan and its last completed result into the detailed distributions, receipt and sample innings. **Edit team plans in Lab** returns an explicit Match draft to the editor. **Save request** exports the normalized draft; full completed-run export remains in Match.

Changing a draft keeps the previous output paired with its submitted inputs and labels it **Inputs changed**. Applying a candidate never updates an old probability. A new successful simulation is required. A/B deltas appear only when both outputs match their drafts, cover the same two teams and share trial count, seed, evidence cutoff, dataset version and model version. Venue, plans and batting-first order may differ. The delta is descriptive; it is not a paired significance test, validated causal effect or demonstrated gain in historical accuracy.

## XI optimization

Choose the team to optimize, one to three candidates, 50–500 trials per candidate, minimum batting coverage and a risk penalty. Lock or exclude players in the searchable pool; **Clear locks and exclusions** resets both lists. The opposing team's complete valid plan is required. The optimized team's current draft may be incomplete because its XI is being generated.

The API's objective combines expected batting and bowling contributions with an uncertainty penalty. It generates constrained proxy candidates, compares their simulated win shares, and independently confirms the selected candidate with another seed. **Recommended** displays this confirmation; alternative tabs display selection-trial estimates. The confirmation applies only to the selected XI and is not historical validation. Small samples can produce noticeably different selection and confirmation shares.

The method disclosure retains returned constraints and reliability notes. A proven proxy optimum is not a proven global maximum in match win probability. Returned batting order is heuristic and captain assignment is a placeholder. The optimizer does not optimize Impact substitutions. Applying its plan replaces that team's XI, order, bowling assignments and substitute/Impact nomination. Application is disabled after the optimizer context changes; rerun it for that context.

Local checks catch common infeasible inputs but do not replicate the full integer solver. A combination of individually plausible locks can still be rejected by the backend. A rejection is displayed without deleting an earlier result or inventing a replacement candidate.

## Sources and failure behavior

`frontend/src/api/snapshots/lab.json` contains ten roster extracts, public role/country/keeper/overseas fields, dated availability status, 37 venues and one real saved optimizer response. It excludes raw pages, source URLs and availability notes. `scripts/export_frontend_lab.py` opens SQLite read-only, records its SHA-256 and validates the saved optimizer request/response. Source paths and hashes are retained. Refresh from the project root:

```powershell
.venv\Scripts\python.exe -m scripts.export_frontend_lab
```

The saved optimizer example comes from `outputs/xi-optimization-request.json` and `outputs/xi-optimization-example.json`; it is labelled separately from a completed API request. The initial A scenario uses the previously documented arbitrary CSK/MI baseline. Neither is a confirmed match-day XI. Selected rosters are refreshed through `/api/v1/teams/{id}/roster?season=2026`, with per-team **Saved roster** or **Local API roster** labels. Snapshot use is explicit. A failed new computation never silently loads a saved forecast.

One planning request can be active in Lab at a time. Waiting is bounded at 45 seconds for simulation and 75 seconds for optimization. **Stop waiting** aborts the browser wait; Python may finish its job and temporarily reject another request with HTTP 429. Cancelled, timed-out and unmounted replies cannot replace later state. Failed requests preserve prior completed results. The interface includes no invented streaming progress.

No pitch/dew/weather sliders, live injury feed, automatic confirmed XIs, player projections or claimed 70% accuracy were added. Historical research remains at its documented 55.7% direct-winner result and is not promoted into planning defaults. Sampling intervals measure finite-trial error, not total predictive uncertainty.

## Validation

The Phase 3 checkpoint had **73 passing tests**, including real optimizer-response integrity, seeded confirmation correspondence, malformed results, roster null classifications, request canonicalization, team-plan edits, interval Impact semantics, bowling constraints, availability, lock/exclusion conflicts, incomplete optimized-side drafts, and comparison freshness/settings/version checks. TypeScript, production build, formatting and exporter lint also passed. The source SQLite SHA-256 matches the Phase 1 extract. See the phase plan for subsequent suite totals.

Focused Chromium checks covered real simulation and one/three-candidate optimizer requests, alternative selection, applying candidates, stale-result labels, matched A/B runs, navigation to Match and back, a real domestic interval Impact run, a solver infeasibility rejection, clearing locks, reversible manual over assignment, cancellation and offline failure recovery. Light/dark layouts were reviewed at 1440px and mobile layouts at 390px/320px without horizontal page overflow. Review images are in `docs/frontend-review/`. These checks do not constitute cross-browser, screen-reader or predictive-model validation.

The user continued after the Phase 3 review checkpoint. See the phase plan for current delivery status.
