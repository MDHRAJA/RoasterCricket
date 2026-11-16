# IPL 2025 match-day evidence pilot

This separate research pack prepares match-day inputs without changing the frozen IPL database or the live model. Read the [pipeline guide](../../docs/prematch-pipeline.md) for definitions, reproduction commands and limitations.

- `prematch.sqlite`: normalized T20 history, season inventory, sourced nominations, dated availability claims and prior-date form snapshots.
- `source_manifest.json`: retained source paths, retrieval times, checksums and failures.
- `official_fixtures.json`: 75 official season inventory entries, including abandoned matches.
- `coverage.json`: measured coverage, source/code hashes and training-readiness decision.
- `lineup_source_candidates.json`: extracted historical reports awaiting evaluation.
- `source_checked_nominations.json`: machine checks and unresolved records, with evidence tiers.
- `lineup_review_queue.json`: missing XI and substitute-list slots.
- `source_review_packet.json`: retained entry text, timestamps and source identifiers inspected for 72 fixtures.
- `lineup_recovery_report.json`: before/after coverage, timestamp limitations, source corrections and three remaining inventory exceptions.
- `match_day_strict.jsonl`: 75 fixture records; 72 have complete lists for both teams after assistant source inspection.
- `match_day_source_checked.jsonl`: 75 fixture records with an explicit machine-check option; the same 72 fixtures currently have complete lists.
- `quality_checks.json`: integrity/date, review-binding, team-membership and training-population audits. The nomination-source research gate now passes for all 68 predefined eligible games.
- `feature_export_coverage.json`: export completeness counts.

The pack includes 10,580 supported men's T20 matches and 294,805 player-innings rows. Both nomination categories have 144/150 source-inspected team slots. The assistant inspected 288 lists, with exact source/record hashes in `research/prematch-2025/source_review_ledger.json`; this is not human certification. Five additional player identities are retained separately, including two local identities without an assumed Cricsheet link. Fourteen date-scoped availability claims are recorded; other player availability remains unknown.

The three incomplete fixtures are 18 April, 8 May and 17 May. Reports after scheduled-start cutoffs remain withheld; no lists are invented for an abandoned fixture. These exceptions are outside the unchanged 68-game training population. Twenty-nine retained lists rely on publisher commentary timestamps without exposed modification histories; all source snapshots were retrieved retrospectively.

Do not interpret source coverage, passing integrity checks or the existence of exports as evidence of prediction accuracy. No model has been retrained or promoted using this pack.

Cricsheet data requires attribution and compliance with its [data license](https://cricsheet.org/licensing/). Raw publisher pages are retained for local research and have separate terms. Do not treat them as freely redistributable data. Raw downloads and SQLite files are excluded from Git.
