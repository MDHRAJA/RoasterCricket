# Phased regression testing

Current pass: 18 November 2026. This is separate from the original frontend build checkpoints in `frontend-phases.md`.

The user requested moving to Phase 2. Remaining real-browser checks from Phase 1 are carried forward; they are not silently counted as passed. Pause for user review before starting Phase 3.

## Phase 2 — Match

Status: automated and live-service checks passed; current browser verification pending.

### Bugs fixed

1. **Draft export lost edited settings.** Editing trials, seed or availability and choosing “Save current request” exported the original loaded request. It now exports the current draft. Invalid seeds disable that export. Completed-request and full-run exports remain tied to their original result.
2. **Winning wide could disappear from the sample timeline.** If a chase ended on an illegal delivery immediately after a completed over, the timeline disabled the next over because its maximum used only legal balls. It now also considers the last physical event's over, displays that delivery and identifies the final legal-ball position.
3. **Response integrity checks accepted misleading data.** Reversed innings, evidence dates at/after the exclusive cutoff, reversed training date ranges, impossible aggregate wickets/balls, misaligned histogram bins and discontinuous traces are now rejected before display. Regression cases failed before the validation changes and pass afterward. This is response protection, not evidence that the deployed backend produced those corrupt responses.

### Functionality checked

| Area | Verified behavior |
| --- | --- |
| Saved example | Correct source, experimental status, exact XI, aggregate totals and histogram counts |
| Controls | Seed zero, invalid seed boundaries, trial changes, availability, stale-result notice, Run setup focus |
| Submission | Complete request, simultaneous double-click guard, busy controls, explicit new-output source |
| Waiting | Cancellation, ignored late reply, retry, 45-second timeout, abort on leaving the workspace |
| Failures | 422/429/500, validation details, offline service, corrupt result, prior completed output retained |
| Keyboard | Space outside controls, typing/repeat suppression, suppression under an open facts dialog |
| Imports | Pasted/file JSON, intermediate trial count, malformed and oversized data, unreadable file, mismatched ground, future evidence, saved-example restoration |
| Exports | Current draft, completed request and complete run decoded and compared with their expected contents |
| Archive/session | 2025 replay controls disabled, recorded facts, expired Lab-session recovery |
| Plans/scorecards | Both teams, batting and bowling, DNB, sample omitted, supplied names, unchanged win estimate during sample navigation |
| Sample timeline | Arrow navigation/focus, innings switch reset, illegal deliveries and final winning-wide boundary |
| Lab handoff | Draft transfer preserves older run as older input; successful scenario completion published once |
| Shared actions | Theme and return callbacks |

### Evidence

- Frontend regression suite: 146 tests passed. Four opt-in live cases skipped in the default run and checked separately.
- Hosted Match service: all four live cases passed (five sequential API requests), including identical seed-zero result data, reverse batting order, optional sample omission, 200-trial output and availability rejection.
- Python simulation/API suites: 93 tests passed. Existing dependency deprecation warning only; no dependency changes in this pass.
- TypeScript, production build and formatting checks passed.
- Fixes published in commit `210e68d48f820909c31f74112a27554e28c7a1ae`. Vercel production deployment `dpl_CDoFyqKWSgUFiCYRkSrVGK46r3Ue` reached READY. Public page, entry script and Match chunk returned HTTP 200. No error/fatal runtime logs were returned for that deployment's checked 15-minute window; this is not a browser console check.

DOM-based tests stub native dialog lifecycle, viewport observation and downloads. Export bytes are decoded; OS download dialogs are not exercised. They cannot establish native Escape/focus containment, visual contrast, touch behavior, responsive geometry or absence of browser console errors.

### Remaining browser checks

- Current hosted Match flow: run setup, real run, cancellation/retry, archive facts and return navigation.
- Native dialog Escape and focus restoration; actual download behavior.
- Desktop/tablet/mobile in both themes, theme persistence and page overflow.
- Fresh browser console check.

Keep Phase 2 open until these are observed. Model prediction accuracy, live match feeds and new prediction features are outside this bug-testing pass.

The current browser observation was rejected by automatic approval review because the available browser window was outside the authorized QA target. Requested a separate Match window from the user. No unrelated page content was inspected and no browser check is marked passed from that attempt.
