# Data dictionary and analytical conventions

Exact columns and row counts are in `dataset_catalog.json`. Dates are ISO strings; blank CSV fields are missing, not zero. Boolean flags are 0/1. Player and match identifiers are strings; do not coerce them into numbers. Read CSV identifiers with explicit string types. SQLite mirrors the processed tables, not the editable manual files.

## Identity and roster tables

| Table | Row grain | Meaning |
| --- | --- | --- |
| `players` | One stable player ID | Source-reported identity, hand, career style, role, country, keeper capability, uncertainty and source URLs |
| `player_aliases` | Player ID + normalized alias | Search/join aliases; the same alias may identify several people, so never assume name uniqueness |
| `player_attributes` | Player ID + factual field | Field-level value and provenance; source observation date is not a historical effective date |
| `metadata_conflicts` | Known player/field conflict | Chosen source label, conflicting source and review note |
| `squads_current` | 2026 team + player | Official website membership snapshot on 2026-10-02; **not** confirmed active registration, fitness or match availability |
| `squads_historical_observed` | Player + raw team name + season | Match-observed membership, first/last listed appearance and appearance count; not a complete historical bench squad |
| `teams` | Franchise ID | Current and defunct franchises. Renamings share IDs; Deccan Chargers and Sunrisers Hyderabad remain distinct |
| `team_aliases` | Source name | Historical name-to-franchise mapping |
| `venues` | Reviewed ground ID | Stadium identity. Aliases are explicit, not fuzzy geographic matches |
| `venue_aliases` | Source stadium label | Original label, city and reviewed canonical key |

`ipl:<official external ID>` identifies current-only players with no safe Cricsheet join. It does not imply fabricated players or failed collection. Similar names are retained separately rather than force-joined. IPL source role remains the current selection-role label; ESPN keeper information may add keeper capability. Country-based `is_overseas` is a research proxy, not proof of legal IPL eligibility under registration rules. Attribute styles can be mixed or missing. `metadata_confidence` and `metadata_conflict` must survive future API/model handling.

## Match-level source tables

- `matches`: one archive match. Calendar `season` is normalized to the year of `match_date`; `season_raw` preserves source labels such as `2007/08`. Raw team/venue labels remain alongside IDs. Toss, result, DLS/method, match number and event stage are retained. Stage can legitimately be blank; do not automatically infer playoffs from match number alone.
- `innings`: one source innings, including Super Overs. Contains total runs, extras-related pre/post penalties, wickets, legal balls, actual delivery count, target and original powerplay definitions as JSON. A revised/DLS target is not a straight 20-over target.
- `deliveries`: one recorded delivery. `delivery_id = match_id:innings:sequence_in_innings`; repeated labels during illegal balls cannot collide. `over_index` is zero-based. `delivery_in_over` is the source-list position, not necessarily legal-ball number. `actual_delivery` preserves source labels when present.
- `wickets`: one dismissal event. Includes dismissed-player and fielders, including non-striker run-outs. Bowler-credit and team-wicket flags are separate. Retired hurt/not out do not count as team wickets; run-outs, retired out and obstructing the field are not credited to the bowler.
- `replacements`: one recorded replacement event, preserving match/role distinction and reason. Some role events have no outgoing-player ID. Recorded match replacements are not automatically equivalent to tactical Impact Player substitutions.
- `match_players`: one match participant named in the archive. Incoming replacements are flagged when recorded; others are `listed_original_or_unresolved`. This is deliberately not labelled a confirmed starting XI.
- `innings_penalties`: pre/post innings penalties if present. Zero rows in this snapshot is a valid empty dataset, not a download failure.
- `season_coverage`: source match counts and date ranges per calendar season; not a comparison against all officially scheduled fixtures.

## Delivery denominators and features

- `legal_ball`: excludes wides and no-balls. Use for overs/economy, not raw delivery-list length. An over is six legal balls; 3.2 overs means 20 legal balls, not 3.2 multiplied by six.
- `ball_faced`: excludes wides and includes recorded no-ball deliveries. This is a declared derived convention; these CSVs are not claimed to be an exact replacement for an official scorecard's scoring adjudications/dead-ball handling.
- `bowler_runs_conceded = total_runs - byes - legbyes - penalty_extras`. Wides and no-ball penalties are included.
- `four`/`six`: actual batter boundaries only. A `runs.non_boundary` flag excludes all-run fours/overthrows from boundary counts.
- `batting_dot`: a faced delivery with zero batter runs. `bowling_dot`: a legal delivery with zero team runs. These are intentionally different.
- `striker_dismissed`: dismissal of the striker on this delivery. Non-striker run-outs belong in player dismissal totals but not striker dismissal rates.
- `score_before`, `wickets_before`, `legal_balls_before`: pre-delivery state, not post-delivery values.
- `phase`: conventional 20-over labels: powerplay overs 1-6, middle 7-16, death 17-20. These fixed labels **are not re-scaled for shortened games**. Use source powerplay definitions/targets to implement shortened-match features later.
- `is_super_over`: Super Overs remain in source tables but are excluded from all ordinary performance aggregates.
- Bowling metadata is career/profile-reported; there is no per-ball pace, length, line, spin direction or tracking data. Historical deliveries enriched with present-day profiles are not time-versioned style observations.

## Descriptive analytical tables

| Table | Grouping/use |
| --- | --- |
| `player_match_stats` | Player + match, linked to team/date/venue; ordinary-innings batting and bowling totals |
| `player_season_stats` | Player + season + team; innings, totals, averages, strike rate and economy |
| `recent_form` | Player + after-match snapshot; last 5/10 actual batting and bowling innings |
| `player_phase_batting` | Batter + season + phase |
| `player_phase_bowling` | Bowler + season + phase |
| `matchups` | Batter + bowler + season + phase |
| `bowler_type_matchups` | Batter + season + phase + reported category/arm/style |
| `batter_hand_matchups` | Bowler + season + phase + batting hand |
| `player_venue_batting` | Batter + venue + season + phase |
| `player_venue_bowling` | Bowler + venue + season + phase |
| `venue_profiles` | Ground-level ordinary-innings scoring/wickets and first-innings summary |
| `venue_phase_profiles` | Ground + season + phase + bowling category |
| `outcome_counts` | Batter + bowler + season + phase + batter runs + striker dismissal; categorical counts, not probabilities |

Aggregate columns retain deliveries, matches, balls faced, legal balls, runs, boundaries, bowler wickets and striker dismissals. `strike_rate = 100*batter_runs/balls_faced`; `economy = 6*bowler_runs_conceded/legal_balls`. `boundary_ball_rate` uses balls faced; `bowling_dot_rate` uses legal balls. Zero denominators produce missing values, never zero performance. Full-season/venue aggregates include all recorded results, including shortened/no-result games; filter source rows for analyses requiring full-length completed innings. `venue_profiles` is descriptive, not a physical pitch classification or causal venue adjustment.

`batted=1` means the player appears at the crease as striker or non-striker. A run-out without facing a delivery is an innings, not DNB. `bowled=1` means at least one recorded bowling delivery. `matches_involved` means source-listed participation, including replacements, not guaranteed original-XI starts. Batting average uses counted dismissals; bowling average uses bowler-credited wickets.

Recent form excludes DNB and did-not-bowl appearances rather than turning them into artificial zero-performance innings. Zero-facing crease appearances remain batting innings. Each window reports its sample count. Recency-weighted runs use weights `0.85**age_in_innings`, normalized over the available window. `runs_trend_per_innings_lastN` is a simple least-squares slope, available with at least three innings; it is not proof of improving future skill. Last-five/ten means appearances in the available IPL archive, not calendar weeks or all-format cricket.

**Training safeguard:** recent-form rows include the named match and are after-match snapshots. Whole-season matchup counts are also retrospective. Recompute from `match_date < prediction_cutoff` for historical evaluation; never feed the target match or future portion of a season into priors/form/context. Source attributes do not establish their values at earlier dates. No Bayesian posterior, calibrated win probability or optimal-XI output has been produced yet.

## Manual input contracts

`manual/availability.csv`: one roster entry, initially `availability=unknown`. Allowed future states: available, unavailable, unknown; record effective date and an attributable source. Role/form does not imply fitness. New snapshot IDs are reconciled while existing user-entered fields and unmatched rows are preserved.

`manual/match_conditions.csv`: an empty, typed scenario template, not a dataset of observed conditions. Team/opponent/venue refer to known IDs. Pitch/dew are user assumptions unless an external measurement is sourced. Toss fields must be confirmed observations when populated. Forecast weather must record its source and retrieval time in future ingestion. Never label scenario assumptions as facts.

Annual overseas/Impact/nomination constraints must be checked against the applicable official playing conditions before the optimizer is enabled. Minimum bowlers, spinners, openers or keeper preferences should be labelled coaching/optimization preferences, not invented league rules. Historical lineup rules need season-specific versions.
