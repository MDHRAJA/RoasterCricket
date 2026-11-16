# IPL dataset foundation

Snapshot collected on **2 October 2026**. This is a real local data pack, not a list of download links. Start with `collection_report.md` for final counts and `dataset_catalog.json` for every table's columns, row count, file size and checksum.

## What is saved

- The complete IPL JSON archive available from Cricsheet at collection time, including its bundled README: 1,243 match records spanning 2008-2026. This is all records in that archive, not a claim that every scheduled, cancelled or abandoned IPL fixture has ball-by-ball data.
- The Cricsheet global player register and aliases, allowing stable player IDs rather than fragile name joins.
- The cricketdata player metadata snapshot: 16,101 global profiles, retained in its original RData format and converted to CSV. Its documentation identifies a 24 March 2025 snapshot.
- Public ESPN athlete JSON profiles and country lookups for IPL participants and identified roster additions; individual retrieval results are recorded.
- Complete squad responses from the official IPL website for all ten 2026 franchises, plus the original page HTML. These responses contain 274 entries, including some replaced/injured players. They are **website roster snapshots, not eligibility lists**.
- Sourced attribute extracts for newer players absent from the older metadata snapshot. Only factual fields and source references are saved; biographies and player images were not copied into these extracts.
- Normalized match, innings, delivery, wicket, participant and replacement tables; player/team/venue identity tables; player attributes and provenance; descriptive recent-form, season, phase, venue, batter-bowler and bowling-type matchup tables.
- An indexed SQLite mirror, collection/checksum manifests, automated validation results and independent archive-to-table tests.
- Editable match-condition and player-availability input templates. Unknown values remain unknown.

## Folder layout

```text
ipl-data/
  raw/                     Original downloads and attributable factual extracts
  processed/               Analysis-ready CSV tables
  manual/                  Match-specific inputs, not invented observations
  ipl.sqlite               Indexed database for the future API
  dataset_catalog.json     Exact row counts, columns and checksums
  source_manifest.json     Main source retrieval records
  enrichment_manifest.json Athlete/country retrieval records
  extra_sources_manifest.json
  documents_manifest.json  Includes refused PDF downloads
  validation_report.json   Build-time reconciliation checks
  independent_tests.json   Read-only raw/archive/database tests
  metadata_review.csv      Missing historical fields/unpublished bowling styles
  identity_issues.json     Conservative identity joins requiring later review
  DATA_DICTIONARY.md
  collection_report.md
```

## Feature readiness

| Planned feature | Saved data | Important limit |
| --- | --- | --- |
| IPL player/season dashboard | Match and player season tables, 2008-2026 | Match archive coverage is not a complete fixture census |
| Recent-form trend | Match timelines; last 5/10 innings; weighted runs and run-trend slope | Descriptive, noisy with few innings; not a forecast |
| Batter vs bowler | Individual matchup counts by season and phase | Small samples require Bayesian shrinkage |
| Batter vs bowling type | Style/category/arm matchup counts | Source-reported career styles, not per-ball variations |
| Bowler vs batting hand | Hand matchup counts | Switch hits are not classified per delivery |
| Venue and phase strengths | Reviewed stadium aliases, venue/phase/player profiles | A venue average is not a measured pitch condition |
| Toss and chasing analysis | Toss, innings, target, result and DLS metadata | Observational correlation is not a causal toss advantage |
| League/playoff filters | Raw event stage and match number | Blank stage is not imputed; Phase 1/2 definitions need explicit product rules |
| Playing XI and Impact scenarios | Roster snapshot, match participants, recorded replacement events | Not every listed participant is an original starting-XI member |
| Player roles, hand and style | Player table, per-field sources and conflict review | Some historical roles and unpublished bowling styles remain missing |
| Pitch/dew/weather scenarios | Explicit manual input schema | No comprehensive observed historical pitch/dew/weather feed collected |
| Injury/availability constraints | All roster members initialized as unknown | Must be verified for a specific match; no real-time injury feed |
| Bayesian probabilities and optimal XI | Underlying event counts and indexed records | Model, calibration, simulator and optimizer are still to be built |
| Upcoming fixtures | Historical match dates only | No invented 2027 fixtures; the official 2026 schedule PDF download was refused |
| IPL eligibility rules | Official 2026 playing-conditions PDF saved, 119 pages; retrieval and verification manifests included | Cover says March 2026, introduction says March 2024; review annual and supplemental Impact regulations before enforcing constraints |

## Rebuild and refresh

The project `scripts/` and `config/` folders contain the collectors, normalization logic, explicit identity/venue overrides and attributable player facts. The portable ZIP includes a copy under `pipeline/`; when using that copy, run the commands from `pipeline/` so it finds the sibling `ipl-data/` folder.

Install `requirements-data.txt` into a Python environment. From the project root:

```text
python scripts/fetch_data.py
python scripts/prepare_players.py
python scripts/enrich_players.py
python scripts/prepare_players.py
python scripts/build_datasets.py
python scripts/test_datasets.py
python scripts/package_data.py
```

Downloads are cached by default. `fetch_data.py --refresh` explicitly downloads the main sources again. Existing availability inputs are preserved by team/season/display-name while identity IDs are reconciled. Snapshot season/date constants are intentionally fixed to this collection: revise them and audit roster changes before a later-season refresh. Reviewed web facts require re-checking their cited profiles; they are not an automatic scraping feed. Document download failures are separately recorded and are not hidden by successful core-data checks.

## Reliability and model-use safeguards

1. Retain the raw archive and source references. Table values can be audited back to a match and delivery sequence.
2. Treat missing fields as missing, not zero, non-bowler, available or fit. Treat provisional/conflicting fields as lower-confidence inputs.
3. Never optimize over all 274 snapshot entries without match-specific eligibility/availability checks.
4. For a historical forecast, filter raw records strictly before the prediction cutoff. Whole-season matchup tables contain that entire season and are not safe pre-match features by themselves.
5. Recent-form rows are **after-match** snapshots and include the match named in `as_of_after_match_id`. Do not use that row to predict the same match. Date-only records cannot establish same-day intra-day ordering; exclude the whole cutoff date for strict historical testing.
6. Present probabilities with uncertainty and sample size. This dataset does not establish predictive reliability; chronological backtesting and calibration come next.
7. The application is franchise selection analytics, not a fantasy XI combining different franchises. Fantasy-platform role quotas are not IPL playing conditions.

## Attribution and redistribution

Primary match source: [Cricsheet IPL downloads](https://cricsheet.org/downloads/), with its [JSON specification](https://cricsheet.org/format/json/). Identity source: [Cricsheet Register](https://cricsheet.org/register/), which states the Open Data Commons Attribution License 1.0. Metadata: [cricketdata](https://github.com/robjhyndman/cricketdata) and its [player metadata documentation](https://pkg.robjhyndman.com/cricketdata/reference/player_meta.html), plus the individually cited ESPN profiles. Current rosters: [official IPL teams](https://www.iplt20.com/teams). Attribute supplements cite official franchises/ICC where available, otherwise identified sports data providers.

This pack is for the user's local research/build. **It is not relicensed as universally open data.** The cricketdata package's GPL-3 code license does not automatically grant rights to ESPN's underlying data. IPL/franchise/provider website terms and data rights separately apply. No explicit match-archive license was found in the downloaded README; preserve attribution and verify permission before commercial use or publishing a downloadable raw-data mirror. Do not commit or publicly host this entire pack without a source-by-source rights review. Do not bypass refusals, authentication or anti-scraping restrictions.
