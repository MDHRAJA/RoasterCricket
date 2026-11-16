# The Concourse — completed frontend

All five frontend phases are complete: Fixtures, Match, Lab, Record, and integration/polish. This is a local interface for the existing IPL data/service. No backend model, research result, serving default or database content changed during the frontend work. No deployment was performed.

## Run locally

From the project root, open two terminals:

```powershell
.\scripts\start_backend.ps1
```

```powershell
.\scripts\start_frontend.ps1
```

Open http://127.0.0.1:5173. The prepared workspace already has its dependencies. Fresh installation is described in [frontend setup](../frontend/README.md).

The backend is needed for new simulations and XI optimization. Fixtures, the saved Match/optimizer examples and Record evidence remain reviewable without it. Each source is labelled; a failed computation never substitutes a saved forecast. The archive is a saved dataset, not a current official schedule or live feed.

## Completed workspaces

| Place | What it provides |
| --- | --- |
| 1 Fixtures | Real 2025/2026 archive, combined filters, recorded match facts and command search. |
| 2 Match | Explicit simulation requests, win shares and sampling intervals, score histograms, run receipt, submitted plans, one sample innings and its scorecard. |
| 3 Lab | Two scenario drafts, team/ground/toss-order controls, manual XI/order/bowling plans, limited domestic interval Impact plans, constrained optimization and descriptive A/B comparison. |
| 4 Record | Separate winner research, simulator backtests and delivery audits, calibration counts, a complete 353-row research ledger and source receipts. |

The Concourse visual system is consistent across these places: condensed signage typography, warm header panels in both themes, rectangular information panels, numbered navigation, team bullets and restrained split-flap values. There are no fabricated live states, unavailable per-trial swarms, projected wagon wheels, measured pitch/dew sliders or invented player forecasts.

Detailed controls and evidence limits: [Match](frontend-match.md), [Lab](frontend-lab.md), [Record](frontend-record.md).

## Navigation and keyboard

- **1–4:** change workspace outside editable controls. Changing workspace returns to the top and moves focus into the newly mounted content. Filtering Fixtures keeps the current input focus.
- **Ctrl/Cmd+K** or **/**: archive search. Arrow keys select results, Enter opens, Escape closes. Numbers typed into an input do not switch workspaces.
- **Escape:** close match facts/search and return focus to the initiating control. Native dialogs contain focus. A search command that navigates instead gives focus to the destination.
- **Space:** run a supplied Match scenario outside interactive controls. The backend returns one complete response; progress counts are not fabricated.
- **Left/right arrows:** choose sample overs when the OverLine is focused. Batting-order strips also have explicit up/down buttons.
- **Skip links:** move focus directly into the current workspace. Exact chart data and wide tables have text alternatives and keyboard-accessible inspection regions.

## Saving plans and recovering

Lab drafts/results persist across navigation within the same page session. Reloading resets planning state. **Save request** in Lab/Match keeps a reusable copy before reloading; **Save full run** in Match keeps its submitted request and response for inspection. Full-run JSON is an evidence export, not a supported run-restore format.

To reuse a saved custom request, choose its teams/ground in Lab, open that scenario in Match and use **Load an explicit scenario request**. Match import checks the request against the current pairing and venue; archive replays also enforce their date and season context. A reloaded temporary Lab match URL now explains **Scenario session ended** and offers a direct return to Lab. It does not pretend to be a missing archive fixture or silently restore a different plan.

Editing inputs or applying a candidate keeps an earlier result paired with its own inputs and marked stale. Run again to update the estimate. Comparison appears only for two fresh runs with matching teams, trial count, seed, cutoff and model/data versions. A descriptive percentage-point change is not a significance test or demonstrated historical benefit.

Only one planning wait can be active in its workspace. **Stop waiting** ignores the response and preserves the previous completed result; Python may finish the computation. Leaving the workspace also aborts its browser wait. Backend rule failures, busy responses and unavailable connections remain explicit. Availability and overseas/role labels are planning proxies, not verified match-day eligibility.

## Final integration changes

- Workspace navigation now resets scroll position and focuses the correct content after lazy loading. Deep Record content no longer leaves Fixtures scrolled at the bottom.
- Dialog cleanup now restores the initiating control before removal; closing match facts/search no longer loses focus to the document body.
- Expired Lab-session and missing-record screens use the correct recovery destination, retain a mobile theme control and wrap long titles within narrow screens.
- Optimizer settings, candidate-pool controls and submission stay compact together. Long candidate output no longer inserts large blank gaps between those controls on tablet/desktop layouts.

## Verification record

The final source passed **86 frontend tests**, TypeScript checking, production build and formatting. All four frontend exporters pass Ruff. Source-artifact hash tests cover the exact saved research files, and the SQLite SHA-256 still matches the initial frontend extract.

Focused Chromium layout checks used fully loaded workspaces at **320, 390, 768, 1024, 1440 and 1920 pixels**. All four workspaces fit without horizontal page overflow. Tables that need more space scroll inside their own panels. Both themes were visually reviewed, with fresh desktop and mobile images retained.

The connected flow was checked with the real Python service: a 50-trial seed-zero run, transfer to Lab, one-candidate optimization, applying its plan with an older result marked stale, a fresh scenario run, a matched A/B batting-first comparison, and returning to Match. The final demonstration used 50 trials/seed zero: A showed a 60% CSK simulated win share and B 72%, with a descriptive +12 percentage-point change. These are finite simulation outputs, not 60%/72% historical prediction accuracy. The independently measured direct-winner study remains **39/70, 55.7%**, below the requested 70% and the same-cohort always-chase baseline.

Cancellation was checked on a 1,000-trial submission: the existing 50-trial result remained intact, including after navigation away. With the owned backend stopped, a failed new scenario request retained its earlier API result and displayed a connection failure. Archive filtering/empty states, the 2025 simulation boundary, recorded scores, command arrows/Enter/Escape, modal focus return, sample-over arrows, scorecard modes, theme persistence and expired-session reload recovery were also checked.

A separate packaged production preview opened Record → Lab → Match → Fixtures, retained correct source/active-navigation labels and reported no browser warnings/errors. The preview intentionally has no API proxy; its Fixtures source was **Saved archive snapshot**. Live computation in a hosted build needs the API routing/configuration described in the frontend guide.

The standard text palette checks met 4.5:1 against their checked surfaces: the lowest was **4.96:1** for light muted text on the alternate panel; panel focus contrast was 5.44:1 light and 10.15:1 dark. Team-bullet contrast is covered by the existing tests. Reduced-motion rules were verified in the stylesheet; OS preference emulation was not performed. This is focused Chromium verification, not a formal accessibility or cross-browser certification. Generated download payloads follow the tested source/export paths; browser download-file contents were not independently inspected in the final pass.

Fonts are local, runtime dependencies remain unchanged, and Match/Lab/Record load as separate chunks. The final main JavaScript chunk is about 89.7 KB gzip; research and planning data are loaded with their workspaces. The code retains reduced-motion styles and avoids background animation or fabricated streaming results.

## Review images

- [Fixtures / dark](frontend-review/final-fixtures-dark.jpg) and [light](frontend-review/final-fixtures-light.jpg): packaged saved archive.
- [Match / dark](frontend-review/final-match-dark.jpg) and [light](frontend-review/final-match-light.jpg): completed hypothetical API run.
- [Match / mobile dark](frontend-review/final-match-mobile-dark.jpg) and [mobile light](frontend-review/final-match-mobile-light.jpg): the same real 50-trial output.
- [Lab / dark](frontend-review/final-lab-dark.jpg) and [light](frontend-review/final-lab-light.jpg): completed A/B scenario runs.
- [Record / dark](frontend-review/final-record-dark.jpg) and [mobile](frontend-review/final-record-mobile-dark.jpg): saved research evidence.
- [Session recovery / mobile](frontend-review/final-session-recovery-mobile.jpg): intentional temporary-scenario reload.

All temporary review servers were stopped after verification. The frontend is complete within the documented backend capabilities; model validation and the unmet prediction-accuracy target remain separate research work.
