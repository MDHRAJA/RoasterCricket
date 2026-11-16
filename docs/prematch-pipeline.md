# Match-day evidence pipeline: IPL 2025 development pilot

The 2025 nomination-source research gate now passes: all 68 games in the previously defined training population have source-inspected original XIs and complete five-player substitute lists. Across the official inventory, 72 of 75 fixtures are covered. The remaining three fixtures stay explicitly incomplete. This gate uses the documented historical publisher-timestamp assumptions; it does not certify immutable pre-match availability of the reports or comprehensive player availability.

This work does not establish any improvement over the previously measured 55.7% winner accuracy. The existing API, simulator, optimizer and selected winner model retain their current behavior. The before/after measurements and source exceptions are saved in `outputs/prematch-2025/lineup_recovery_report.json`.

## Collected coverage

The generated pack lives in `outputs/prematch-2025/`. Its canonical machine-readable summary is `coverage.json`.

| Item | Coverage in this build |
| --- | --- |
| Official 2025 fixture inventory | 75 entries |
| Fixtures represented in frozen ball-by-ball data | 74 |
| Supported men's T20 matches, all available competitions | 10,580 |
| Player-innings rows | 294,805 |
| Starting-XI team slots with timestamp/source checks | 144 / 150, previously 103 |
| Substitute-list team slots with timestamp/source checks | 144 / 150, previously 81 |
| Assistant source-inspected team slots, each list category | 144 / 150 |
| Fixtures with all four lists source-checked | 72 / 75, previously 30 |
| Fixtures with all four lists directly source-inspected | 72 / 75, previously 1 |
| Previously defined training-eligible games with all four lists source-checked | 68 / 68 |
| Training-eligible games with all four lists directly source-inspected | 68 / 68 |
| Reviewed date-scoped availability claims | 14 |
| Form snapshots across selection bases | 4,025 |
| Snapshots containing non-IPL history | 2,567 |
| Snapshots with no recent batting or bowling history | 182 |

A team slot means one team's list in one fixture; two teams across 75 inventory entries give 150 slots per list category. Snapshot counts include repeated players across fixtures and selection bases, rather than unique people. Competition labels include tours and series, rather than representing distinct leagues.

The unmatched fixture is RCB–KKR on 17 May 2025, officially abandoned without a ball bowled. It retains its official identifier and explicit missing ball-data status. The other two incomplete fixtures are rain-delayed RCB–PBKS on 18 April and the abandoned PBKS–DC fixture on 8 May: retained nomination reports after the scheduled-start cutoffs are withheld. The 24 May replay is a separate covered fixture. No lineup or statistic is invented for an incomplete slot.

The 68-game training denominator follows the existing uninterrupted-match evaluation eligibility rules; it was not narrowed to obtain complete coverage. Other excluded fixtures can still have complete nomination-source records. Passing this coverage gate is limited to nomination inputs, rather than every planned feature.

## Evidence tiers and time cutoffs

`backend/match_day_inputs.py` reads only prepared, eligible sources. Its default requires directly inspected timestamped reports. Inspection was performed by the assistant; no human certification is claimed. Machine-checked sources require the explicit `allow_machine_checked=True` option and all seven recorded cross-checks. Missing evidence produces empty lists and an incomplete flag. Retrospective reconstructed starters are stored separately for conditional diagnostics and never fill a missing sourced XI.

Machine checks require a uniquely matched fixture/team, a complete list of uniquely resolved identities, the publisher's entry timestamp and any exposed modification timestamp before the scheduled start, agreement between an original XI and the separate ball-data reconstruction, substitutes disjoint from that original XI, and no known conflict with independently recorded 2025 team membership. Candidate reports must fall in the declared one-hour pre-start window. Projected lineups and conflicting lists are withheld. The reconstruction and team-membership comparisons are retrospective consistency audits, not dated availability features or proof of historical publication. Incoming Impact Players are not substituted into the original XI.

Historical reports were retrieved now, rather than captured immutably at announcement time. Even a checked publication/modification timestamp cannot exclude a silent retrospective edit. Of the 288 retained lists, 259 have declared publication/modification fields and 29 use publisher commentary timestamps without exposed modification histories. The basis and missing modification metadata are visible in the exports. A publisher's current page headline can also describe a later result; those headlines are not prediction features.

Direct inspection examines retained entry text, nomination wording, times, identities and fixture context. `source_review_packet.json` records the inspected entries, and `research/prematch-2025/source_review_ledger.json` binds all 288 decisions to exact nomination and source hashes. Changed evidence invalidates its review. The assistant caught a report that swapped PBKS and KKR bench labels on 15 April; the new team-membership check rejects it, and a correctly labelled independent report supplies both lists. A missing comma between the complete names Rovman Powell and Luvnith Sisodia is explicitly documented as a source-inspected punctuation correction. Partial reports with an actually missing name remain incomplete.

Scheduled-start cutoffs can withhold valid reports from delayed fixtures. The review queue represents evidence not established under this policy, rather than automatically proving that no source exists. Research trained on this pack must disclose these timestamp assumptions; passing the gate is not a proof of leak-free historical observability.

Recent form uses available Cricsheet men's, six-ball, scheduled-20-over matches. It excludes women's cricket, other formats, five-ball competitions and Super Overs. The default window is the prior 365 days and the last ten actual batting innings and last ten bowling innings independently. A completed match must have a completion date strictly before the target date. Same-day results and future matches are excluded. DNB is not a zero-run innings; undefined rates remain null. Player identities use stable IDs and reviewed aliases.

Match-score publication timestamps are not reconstructed. This pilot assumes a complete prior-date score was observable after match completion. Cricsheet coverage is extensive but is not complete global T20 coverage. League strength adjustment is not yet modeled in these raw form summaries.

Availability claims preserve the publication date, effective interval, team/season, source and any match-only or playoff-only scope. Publication-day claims with no reliable time are withheld for that entire date. Future announced departures do not apply before their effective date. The latest eligible dated claim governs; same-date contradictory claims remain conflicting. Unknown availability stays unknown. Qualified return reports retain qualified status and do not become medical clearance. Fourteen claims are a seed ledger, not comprehensive injury, suspension, squad-registration or eligibility coverage.

## Sources and artifacts

The collector retains the [Cricsheet men's download](https://cricsheet.org/downloads/), the original frozen IPL archive, public official IPL season/scorecard feeds, official IPL/team and ICC news, and timestamped reports from Indian Express, India Today, Times of India and public Cricbuzz pre-match commentary. Older updates come from exposed public archive/load-more pages. Cricbuzz fixture IDs are matched by date and teams through its public season index. Each retained download has a retrieval time and SHA-256 checksum in `source_manifest.json`; failed fetches remain explicit. Three NDTV requests returned HTTP 403 and were left unavailable without retrying them through alternate routes.

Cricsheet match data uses the license described on its [licensing page](https://cricsheet.org/licensing/); preserve attribution and applicable notices. Publisher HTML has separate terms and is a local evidence cache, not a freely redistributable data pack. Avoid publishing raw third-party caches without reviewing the applicable rights.

The generated database contains `t20_matches`, `t20_player_innings`, `pilot_matches`, `nominations`, `availability_claims`, `player_form_snapshots` and `additional_player_identities`. The reviewed configuration is `research/prematch-2025/evidence.json`. Five supplementary identities retain franchise provenance; three link to reviewed Cricsheet register IDs, while Manvanth Kumar and Swastik Chikara use separate local IDs with no invented linked history. Identity metadata does not establish a player's past availability.

`source_checked_nominations.json` retains accepted and unresolved machine checks; `lineup_review_queue.json` lists missing slots. Both JSONL exports contain all 75 fixtures with completeness flags, rather than silently dropping incomplete fixtures.

Builds use a temporary database, validate source hashes and replace the new pack database on success. The existing `outputs/ipl-data/ipl.sqlite` is opened read-only and its hash must remain unchanged. Source/code hashes in `coverage.json` identify the exact build inputs.

## Reproduce locally

From the project root with the existing virtual environment and retained sources/review ledger, replay the audited pack without network access:

```powershell
.venv\Scripts\python.exe scripts/build_prematch_pack.py
.venv\Scripts\python.exe scripts/export_match_day_inputs.py
.venv\Scripts\python.exe scripts/check_prematch_pack.py --require-training-ready
.venv\Scripts\python.exe scripts/report_lineup_recovery.py
```

For a new collection, the original frozen IPL pack must already exist. Collect sources and recover older entries sequentially:

```powershell
.venv\Scripts\python.exe scripts/collect_prematch_sources.py --all-male --ipl-season --claims --identities
.venv\Scripts\python.exe scripts/discover_matchday_reports.py
.venv\Scripts\python.exe scripts/collect_matchday_pages.py
.venv\Scripts\python.exe scripts/collect_matchday_recovery.py
.venv\Scripts\python.exe scripts/collect_public_liveblog_pages.py
.venv\Scripts\python.exe scripts/discover_matchday_reports.py --cached-only
.venv\Scripts\python.exe scripts/check_nomination_sources.py
.venv\Scripts\python.exe scripts/collect_cricbuzz_matchday.py
.venv\Scripts\python.exe scripts/discover_matchday_reports.py --cached-only
.venv\Scripts\python.exe scripts/check_nomination_sources.py
```

Cached sources are reused rather than silently refreshed. Current network pages can differ from retained historical-source snapshots, so a fresh collection may require renewed inspection. Never copy approvals onto changed sources. Build unreviewed inputs with `build_prematch_pack.py --stage-review`, prepare a packet with `review_nomination_sources.py --prepare`, inspect its numbered batches with `--batch N`, and record only the fixture IDs actually inspected using `--record-inspected id1,id2,...`. Preparing/displaying packets does not grant approval. A staging build deliberately keeps the strict coverage gate closed. Run the ordinary replay commands after completing the new inspection.

Validation for this recovery: all 195 tests passed, including parser separation, projected-choice exclusion, team-label conflict detection and review-digest tampering checks. Ruff passed. The exact data-audit count is in `quality_checks.json`; the nomination-source gate reproduces all 68 eligible games. These are implementation and data checks, rather than new accuracy measurements.

## Remaining work before a new accuracy experiment

The immediate 2025 nomination gap is closed for the fixed training population. Broaden the dated availability ledger and obtain earlier development seasons with the same safeguards. The three inventory exceptions need a separately declared delayed-start policy and appropriate sources if they are to be analyzed; do not silently change the current cutoff or eligibility policy to admit them.

Before retraining, define a prediction cutoff, a coverage policy and an evaluation protocol. Compare feature additions on development data, report coverage and calibration alongside accuracy, and lock selection before evaluating an untouched future period. The previously inspected 2026 season cannot serve as a fresh untouched holdout. Reaching 70% cannot be guaranteed by collecting these inputs.
