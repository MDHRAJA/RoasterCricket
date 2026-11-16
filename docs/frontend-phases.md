# Frontend delivery phases

The user requested sequential phases and explicitly asked to pause for review after each one. The visual direction is **The Concourse**: public-wayfinding typography and information hierarchy, literal cricket terminology, dense rectangular sign panels, route bullets and restrained split-flap numerals. This remains a local frontend for the existing Python service.

## 1. Foundation and Fixtures — reviewed; continued by user

- React, TypeScript and Vite; self-hosted Barlow, Barlow Condensed and IBM Plex Mono. Condensed Barlow provides the narrow, heavy signage voice while preserving enough room for long franchise names.
- Separate light and dark compositions. Dark mode retains a warm-white title sign; yellow indicates the selected filter/place/action. Team colors are restricted to small team bullets.
- Responsive vertical numbered navigation becomes bottom navigation on mobile. Reusable SignPanel, RouteBullet, TagToggle, ServiceNote, SplitFlap, LineKey, DeparturesBoard and CommandKiosk components.
- Real 2025/2026 archived matches, recorded scores and margins, reverse date grouping, filters, empty states, incremental rows, shareable filters and match-record dialog. Upcoming fixtures and live statuses are omitted because no feed exists.
- Typed read-only API connection with a bounded connection check and labelled saved fallback. Extract provenance and source-database hash are retained.
- Native modal focus handling, keyboard navigation, searchable commands, persisted theme, custom geometric cricket pictograms and reduced-motion behavior.
- 19 automated tests; production build and formatting checks. Browser evidence is stored in `docs/frontend-review/`. Checked desktop (1440px) and mobile (390px and 320px), both themes, theme persistence, filters and empty states, keyboard search, arrow/Enter row navigation, Escape, match facts, pagination and saved-snapshot fallback. No browser warnings or errors were observed in the final production-preview check. This is a focused Chromium preview check, not a full cross-browser or assistive-technology audit.

No prediction or modeling code was changed. The existing research accuracy and promotion restrictions remain in effect. This phase does not establish a prediction service's readiness or create historical forecasts from observed outcomes.

## 2. Match — reviewed; continued by user

The Match workspace now presents win probabilities, 95% Monte Carlo sampling intervals, unresolved ties, shared-axis score histograms, innings quantiles, submitted plans, an evidence receipt and one sample match. A native SVG histogram is redrawn at the panel's actual width, with exact bin-count tables available as text. The verdict precedes run setup on narrow screens. Light and dark modes retain the Concourse panel system.

Run setup supports the API's 50–1,000 trial range, seed 0–4,294,967,295 and explicit unknown-availability assumption. New requests go to the existing computation endpoint. Previous results retain their exact submitted inputs, including after a failed or cancelled wait. Double submissions are blocked; unmount/cancelled replies cannot overwrite later state. Waiting is bounded at 45 seconds. Stopping the browser wait does not terminate the backend job.

A closer inspection during this phase confirmed that `sample_match.innings[].deliveries` contains the first trial's event trace. The 20-station OverLine therefore scrubs that **single sample innings**, including illegal deliveries and early innings endings. It does not change pre-match win probabilities or claim to be an aggregate probability-over-time curve. The sample scorecard separates batting/bowling, keeps DNB distinct from zero and identifies sample-only outcomes. Aggregate player projections are absent from this API and are omitted.

The example is the project's existing hypothetical CSK/MI request and saved output, with source-file hashes retained. It is labelled a saved run until a live request completes. Archived fixtures instead open a replay workspace with recorded facts available separately. They require explicit, matching team/venue plans and a cutoff on or before the recorded date; participants are never silently promoted to a confirmed XI. The 2025 archive remains viewable but its simulator controls are unavailable. Scenario requests can be imported/pasted and exported; completed runs can be saved with their exact request and response.

Validation: 46 frontend tests; TypeScript/production build; formatting; exporter lint; live 50- and 200-trial browser runs; repeated seed; rejected availability assumption; cancellation; malformed/valid imports; scorecard modes; exact histogram data; archive record dialog; light/dark and narrow-screen checks. The source SQLite hash still matches Phase 1. Browser evidence is saved under `docs/frontend-review/`. This is focused Chromium QA, not a cross-browser or formal accessibility certification. See [Match workspace guide](frontend-match.md).

The user continued to Phase 3 after this checkpoint.

## 3. Lab — reviewed; continued by user

Lab now connects separate A/B drafts, ten roster proxies, 37 grounds, explicit batting-first scenarios, starter selection, captain nomination, batting order, twenty bowling assignments and the supported domestic interval Impact plan. Arrow buttons accompany drag reordering. Unknown dated availability requires an explicit assumption; profile labels do not imply verified match-day eligibility. No unsupported pitch/dew/weather or injury controls were added.

XI optimization exposes candidate count, trials, risk penalty, batting coverage and player locks/exclusions. Results distinguish candidate-selection estimates from independent selected-XI confirmation. The returned method/constraints remain visible. A proxy optimum is not claimed to maximize global win probability. Applying a candidate replaces that team's complete plan, keeps its older simulated result visibly stale and requires a new run. Lab/Match navigation retains scenario drafts, results and the last completed optimizer response within the page session; reload resets planning state.

Comparison requires fresh A/B outputs with matching teams, trial count, seed, cutoff, dataset and model versions. It shows a descriptive difference rather than a significance or causal claim. One bounded planning wait can run at a time; failure/cancellation preserves completed outputs and ignores late replies. Backend infeasibility is surfaced without inventing an XI.

Validation: 73 frontend tests, TypeScript/production build, formatting, exporter lint and unchanged source-database SHA-256. Focused Chromium checks covered real simulations, one/three-candidate optimization, alternatives, application/staleness, matched A/B runs, Lab/Match round trips, a real interval Impact run, a real solver rejection, clearing locks, manual bowling edits, cancellation and backend-offline recovery. Both themes were reviewed at 1440px; mobile at 390px and 320px had no horizontal page overflow. No browser warnings/errors were observed before the intentional offline check. Screenshots are saved as `docs/frontend-review/phase3-lab-*.jpg`. See the [Lab guide](frontend-lab.md) for source manifests, controls and exact limitations.

The user continued to Phase 4 after this checkpoint. This phase changed no model, measured prediction accuracy or database contents.

## 4. Record — reviewed; continued by user

Record now presents separate winner-research, full-match simulator and delivery-calibration views from a labelled saved extract. The direct winner study displays 39/70 (55.7%) beside the stronger 45/70 chasing baseline and explicitly marks the 70% target missed. Chronological protocol, selection/final season rows, Brier/log loss, paired comparison intervals and serving status remain visible. No research model is promoted into Match/Lab.

Native responsive SVG calibration plots use actual fixed-bin counts, observed batting-first outcomes and approximate Wilson whiskers. Exact tables accompany interactive points/bin selectors. No unavailable fitted band is fabricated. The 353-row research ledger supports chronological Right/Wrong strips, season selection, search, filtering, additional rows and forecast receipts with focus return. Missing selection-fold traces are labelled absent. Filters never alter headline cohorts.

Simulator views retain variant-specific cohorts, baselines, half-credit tie convention, exclusion accounting and the limited participant-pool scope. The first-innings score audit pairs coverage improvements with wider intervals, point errors and interval scores. Delivery improvements retain match-cluster uncertainty and separate delivery units. Source hashes, saved integrity checks, limitations and complete public-extract export are available in the receipt.

Validation: 86 frontend tests, TypeScript/production build, formatting, exporter lint and unchanged SQLite digest. Local Chromium checks covered evidence/season/variant switches, calibration selection and keyboard operation, exact data, forecast filtering/empty states, receipts/focus, source disclosure, export activation, numbered navigation, reload/theme persistence and operation with Python stopped. Both themes were reviewed at 1440px; 390px/320px layouts had no horizontal page overflow. Final fresh loading produced no browser warnings/errors. Download-file contents were not independently inspected. Screenshots are saved as `docs/frontend-review/phase4-record-*.jpg`. See the [Record guide](frontend-record.md).

The user continued to Phase 5 after this checkpoint. No model, measured accuracy, backend default or database content was changed.

## 5. Final integration and polish — complete

The integrated flow has been reviewed in both themes, across 320–1920px widths, using the live Python service and a separate packaged preview. Navigation now resets scroll and focuses new workspace content; native dialogs restore focus on close; expired Lab-session links have accurate recovery and responsive titles; optimizer controls stay compact beside long candidate output.

Final checks: 86 passing frontend tests, TypeScript/production build, formatting, exporter lint and unchanged SQLite digest. Browser checks included real seed-zero simulation/optimization, stale-result handling, matched A/B runs, return to Match, cancellation/navigation away, backend-offline recovery, archive facts and 2025 boundaries, command/modal keyboard behavior, sample controls and theme/reload behavior. Fully loaded Fixtures, Match, Lab and Record fit 320, 390, 768, 1024, 1440 and 1920px without horizontal page overflow. The packaged cross-workspace check showed no browser warnings/errors. Standard text palette contrast passed the checked thresholds; reduced-motion stylesheet rules were verified without OS preference emulation.

Final review images are saved under `docs/frontend-review/final-*.jpg`. See the [completed frontend guide](frontend-release.md) for startup, supported flows, storage behavior, detailed verification and remaining model limitations. All five frontend phases are complete. No model promotion, accuracy improvement or deployment is implied; temporary review servers were stopped.

## Brief adaptations

- A saved match archive replaces a fictional departures schedule. Actual scores replace fabricated pre-match percentages in Fixtures. Dates and source IDs replace invented kickoff times/platform numbers.
- The phase-1 Match dialog remains available as recorded facts inside the new archive replay workspace. Hypothetical simulation results are shown separately.
- Command search supports real matches, teams and grounds. Player jumping and natural-language what-if commands remain absent until their actual destinations and parsers exist.
- Shot-direction wagon wheels, fantasy ownership, live feed labels, measured dew/pitch controls, aggregate player projections and unavailable per-trial swarms are omitted. A single provided sample trace supports the limited sample-only OverLine; no missing ensemble data is reconstructed.
- Custom SVG pictograms and split-flap animation are implemented directly in code; no decorative bitmap assets or icon library is needed.

## Local review

Run `./scripts/start_frontend.ps1` from the project root. Start the backend separately with `./scripts/start_backend.ps1` when API mode is wanted. See [frontend setup](../frontend/README.md) for fresh installation, checks, source labels and production-preview behavior.
