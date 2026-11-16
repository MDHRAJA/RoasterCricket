# IPL data collection report

Collected 2 October 2026. Core data is saved locally and validated. This report distinguishes collected facts, derived descriptions and outstanding inputs.

## Saved coverage

- 1,243 Cricsheet IPL match records across 19 seasons (2008-2026).
- 295,732 recorded deliveries, including separately flagged Super Overs.
- Date range: 2008-04-18 to 2026-05-31.
- 840 player identities: 809 with archive participation and 31 additional snapshot players.
- Ten official 2026 roster snapshots, 274 entries. These include replaced players and are not an eligibility/fitness list.
- 37 reviewed stadium identities from 60 original labels.
- 31 processed CSV datasets plus an indexed SQLite mirror.
- Build checks: 18/18; independent tests: 12/12.

## Player metadata coverage

- Batting hand and primary role are sourced for all 274 snapshot members; no missing batting hands across the 840-player master.
- All 147/147 officially labelled roster bowlers/all-rounders have a reported bowling category.
- 29 current snapshot batters/keepers have no published bowling style in the selected sources; this does not mean they cannot bowl.
- 42 historical player primary roles remain unpublished in the collected metadata. See metadata_review.csv; do not guess them from observed wickets/runs.
- 18 current players retain stable official IPL local IDs because a safe Cricsheet identity join was not established.
- One explicit bowling-style conflict: Daksh Kamra (official KKR Off Spin vs Cricbuzz legbreak). Retain spin/right-arm at coarse level; review before fine-grained modelling.
- Amit Kumar (SRH) supplemental attributes are provisional secondary-source facts, not an official IPL profile; identically named players were not merged.
- Historical delivery bowling-category coverage: 99.99763%. Career categories are not ball-level tracking measurements.

## Descriptive features ready for development

Player season and match statistics; last-5/10 form timelines and run-trend slope; batter-bowler and bowling-style/hand matchups; powerplay/middle/death phase splits; player/venue profiles; toss/result/target fields; wicket/fielding and replacement events. Raw stage metadata supports stage filters where supplied.

These are descriptive inputs. No Bayesian posterior, simulated win probability or optimized XI has been calculated. Whole-season aggregates and after-match form must not leak into historical pre-match predictions.

## Outstanding or unavailable layers

- Match-day registration/fitness/injuries/availability: manual template initialized to unknown; no comprehensive live feed collected.
- Measured historical pitch state, dew and weather: not in ball-by-ball archive; empty scenario-input template provided.
- Upcoming fixtures: no invented future-season schedule. The identified 2026 schedule document was a partial initial schedule and could not be downloaded.
- Full historical registered/bench squads: match-observed membership is collected instead; do not equate it with all contracted players.
- Official 2026 playing-conditions PDF: saved unmodified (119 pages) through the download link embedded in the official IPL page. Cover says effective March 2026; introduction says March 2024. See rules_document_verification.json. Annual constraints and any supplemental Impact Player regulations still require review before implementation.
- Fielding events outside dismissals, tracking metrics and per-ball style changes: absent from selected sources.

### Original document-server download attempts

- [TATA_IPL_2026_Match_Playing_Conditions.pdf](https://documents.iplt20.com/bcci/documents/1774265031558_TATA_IPL_2026_Match_Playing_Conditions.pdf): HTTP Error 403: Forbidden. Reference logged; this binary PDF is **not saved**.
- [TATA_IPL_2026_Match_Playing_Conditions_current.pdf](https://documents.iplt20.com/bcci/documents/1775736835406_TATA_IPL_2026_Match_Playing_Conditions.pdf): HTTP Error 403: Forbidden. File subsequently saved through the public official IPL website download link; original refused attempt retained for audit.
- [TATA_IPL_Schedule_2026.pdf](https://documents.iplt20.com/bcci/documents/1774332251856_1773233174530_TATA-IPL-Schedule-2026.pdf): HTTP Error 403: Forbidden. Reference logged; this binary PDF is **not saved**.

The collected official rules PDF is [saved here](raw/ipl/TATA_IPL_2026_Match_Playing_Conditions_current.pdf). Its successful retrieval URL, byte count and SHA-256 are recorded in rules_download_manifest.json.

## Dataset inventory

| Dataset | Rows | Local file |
| --- | ---: | --- |
| players | 840 | [players.csv](processed/players.csv) |
| squads_current | 274 | [squads_current.csv](processed/squads_current.csv) |
| squads_historical_observed | 3,354 | [squads_historical_observed.csv](processed/squads_historical_observed.csv) |
| player_attributes | 4,074 | [player_attributes.csv](processed/player_attributes.csv) |
| player_aliases | 2,826 | [player_aliases.csv](processed/player_aliases.csv) |
| metadata_conflicts | 1 | [metadata_conflicts.csv](processed/metadata_conflicts.csv) |
| matches | 1,243 | [matches.csv](processed/matches.csv) |
| innings | 2,514 | [innings.csv](processed/innings.csv) |
| deliveries | 295,732 | [deliveries.csv](processed/deliveries.csv) |
| wickets | 14,705 | [wickets.csv](processed/wickets.csv) |
| replacements | 624 | [replacements.csv](processed/replacements.csv) |
| match_players | 27,909 | [match_players.csv](processed/match_players.csv) |
| innings_penalties | 0 | [innings_penalties.csv](processed/innings_penalties.csv) |
| teams | 15 | [teams.csv](processed/teams.csv) |
| team_aliases | 19 | [team_aliases.csv](processed/team_aliases.csv) |
| venue_aliases | 60 | [venue_aliases.csv](processed/venue_aliases.csv) |
| venues | 37 | [venues.csv](processed/venues.csv) |
| venue_profiles | 37 | [venue_profiles.csv](processed/venue_profiles.csv) |
| venue_phase_profiles | 1,180 | [venue_phase_profiles.csv](processed/venue_phase_profiles.csv) |
| player_match_stats | 27,909 | [player_match_stats.csv](processed/player_match_stats.csv) |
| player_season_stats | 3,354 | [player_season_stats.csv](processed/player_season_stats.csv) |
| recent_form | 27,909 | [recent_form.csv](processed/recent_form.csv) |
| player_phase_batting | 6,231 | [player_phase_batting.csv](processed/player_phase_batting.csv) |
| player_phase_bowling | 5,352 | [player_phase_bowling.csv](processed/player_phase_bowling.csv) |
| matchups | 65,255 | [matchups.csv](processed/matchups.csv) |
| bowler_type_matchups | 32,906 | [bowler_type_matchups.csv](processed/bowler_type_matchups.csv) |
| batter_hand_matchups | 9,895 | [batter_hand_matchups.csv](processed/batter_hand_matchups.csv) |
| player_venue_batting | 18,997 | [player_venue_batting.csv](processed/player_venue_batting.csv) |
| player_venue_bowling | 18,161 | [player_venue_bowling.csv](processed/player_venue_bowling.csv) |
| outcome_counts | 161,352 | [outcome_counts.csv](processed/outcome_counts.csv) |
| season_coverage | 19 | [season_coverage.csv](processed/season_coverage.csv) |

## Sources and use

Match data: [Cricsheet](https://cricsheet.org/downloads/). Stable identities: [Cricsheet Register](https://cricsheet.org/register/). Base metadata: [cricketdata](https://github.com/robjhyndman/cricketdata), with 2025 snapshot documentation. Updated attributes: saved public ESPN JSON profiles plus individually cited ICC/franchise/provider facts. Rosters: [official IPL teams](https://www.iplt20.com/teams). See the raw manifests and per-field sources for exact URLs and retrieval checksums.

Source-specific attribution and terms apply. This local pack is not universally open-licensed; review redistribution/commercial rights before public deployment. Source PDFs that refused access have not been bypassed.

Read [DATA_DICTIONARY.md](DATA_DICTIONARY.md) for denominator/phase/identity definitions, and [README.md](README.md) for rebuild steps and the complete readiness matrix.

Next development boundary: an API over the validated database, then time-safe Bayesian modelling and calibration; frontend work can proceed with these real records without fabricated forecasts.
