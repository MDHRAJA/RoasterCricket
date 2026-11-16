import copy
import json
import sqlite3

import pytest

from backend.match_day_inputs import match_day_inputs
from backend.prematch_data import (
    SCHEMA,
    availability_as_of,
    insert_dict,
    nomination_eligible,
    nomination_review_digest,
    normalized_t20,
    player_form,
    team_membership_conflicts,
)
from scripts.check_nomination_sources import names_in_list, segments, without_projected_choices
from scripts.collect_public_liveblog_pages import archive_links
from scripts.discover_matchday_reports import candidates_from_html


def document():
    people = {n: n.lower() for n in ("A", "B", "C", "D", "W")}

    def ball(batter="A", non_striker="B", bat=0, total=0, **extra):
        return {
            "batter": batter,
            "non_striker": non_striker,
            "bowler": "W",
            "runs": {"batter": bat, "total": total, "extras": total - bat},
            **extra,
        }

    deliveries = [
        ball(bat=4, total=4),
        ball(bat=6, total=7, extras={"noballs": 1}),
        ball(total=1, extras={"wides": 1}),
        ball(total=2, extras={"byes": 2}, wickets=[{"player_out": "B", "kind": "run out"}]),
        ball(non_striker="C", wickets=[{"player_out": "A", "kind": "caught"}]),
        ball(batter="C", non_striker="D", wickets=[{"player_out": "C", "kind": "retired hurt"}]),
    ]
    return {
        "info": {
            "gender": "male",
            "match_type": "T20",
            "balls_per_over": 6,
            "overs": 20,
            "dates": ["2025-03-01"],
            "registry": {"people": people},
            "teams": ["One", "Two"],
            "event": {"name": "Domestic test fixture"},
            "team_type": "club",
        },
        "innings": [{"team": "One", "overs": [{"over": 0, "deliveries": deliveries}]}],
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("gender", "female"),
        ("match_type", "ODI"),
        ("match_type", "Test"),
        ("balls_per_over", 5),
        ("overs", 10),
    ],
)
def test_non_target_formats_cannot_enter_t20_form(field, value):
    doc = document()
    doc["info"][field] = value
    assert normalized_t20("1", doc, source_file="fixture") is None


def test_run_wicket_and_actual_appearance_conventions():
    doc = document()
    doc["innings"].append({**copy.deepcopy(doc["innings"][0]), "super_over": True})
    _, rows = normalized_t20("1", doc, source_file="fixture")
    players = {r["player_id"]: r for r in rows}
    assert players["a"]["batting_runs"] == 10 and players["a"]["balls_faced"] == 4
    assert players["b"]["batted"] == 1 and players["b"]["balls_faced"] == 0
    assert players["b"]["dismissals"] == 1
    assert players["c"]["dismissals"] == 0
    assert players["w"]["legal_balls_bowled"] == 4
    assert players["w"]["runs_conceded"] == 12
    assert players["w"]["bowler_wickets"] == 1
    assert len(rows) == 5


def test_form_uses_completion_date_and_excludes_same_day_and_future():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    for mid, days in (
        ("old", ["2025-03-01"]),
        ("spanning", ["2025-03-02", "2025-03-05"]),
        ("same-day", ["2025-03-04"]),
        ("future", ["2025-04-01"]),
    ):
        doc = document()
        doc["info"]["dates"] = days
        match, rows = normalized_t20(mid, doc, source_file="fixture")
        insert_dict(db, "t20_matches", match)
        for row in rows:
            insert_dict(db, "t20_player_innings", row)
    form = player_form(db, "a", "2025-03-04")
    assert form["source_match_ids"] == ["old"]
    assert form["batting_innings"] == 1 and form["bowling_innings"] == 0
    assert form["bowling"]["legal_balls_bowled"] == 0
    assert form["economy"] is None
    zero_ball = player_form(db, "b", "2025-03-04")
    assert zero_ball["batting_innings"] == 1 and zero_ball["strike_rate"] is None
    assert player_form(db, "never_played", "2025-03-04")["source_match_ids"] == []
    with pytest.raises(ValueError, match="Invalid form"):
        player_form(db, "a", "2025-03-04", count=0)
    db.close()


def claim(**changes):
    return {
        "claim_id": "c",
        "season": 2025,
        "team_id": "GT",
        "player_id": "buttler",
        "published_on": "2025-05-15",
        "effective_from": "2025-05-26",
        "status": "reported_unavailable",
        **changes,
    }


def test_effective_date_does_not_backdate_announced_absence():
    claims = [claim()]
    assert availability_as_of(claims, "GT", "buttler", "2025-05-15")["status"] == "unknown"
    assert availability_as_of(claims, "GT", "buttler", "2025-05-25")["status"] == "unknown"
    assert (
        availability_as_of(claims, "GT", "buttler", "2025-05-26")["status"]
        == "reported_unavailable"
    )
    assert (
        availability_as_of([claim(published_on="2025-05-26")], "GT", "buttler", "2025-05-26")[
            "status"
        ]
        == "unknown"
    )
    assert availability_as_of(claims, "GT", "missing", "2025-05-26")["status"] == "unknown"
    assert availability_as_of(claims, "GT", "buttler", "2026-05-26")["status"] == "unknown"


def test_availability_conflicts_and_specific_scope_remain_explicit():
    claims = [claim(), claim(claim_id="conflict", status="reported_available")]
    assert availability_as_of(claims, "GT", "buttler", "2025-05-27")["status"] == "conflicting"
    assert (
        availability_as_of(
            [claim(only_match_id="m")], "GT", "buttler", "2025-05-27", match_id="other"
        )["status"]
        == "unknown"
    )
    assert (
        availability_as_of(
            [claim(stage_scope="playoffs")], "GT", "buttler", "2025-05-27", stage=""
        )["status"]
        == "unknown"
    )


def test_nomination_timestamps_and_later_edits_are_gated():
    record = {"status": "timestamped_report_reviewed", "published_at": "2025-03-22T19:23:26+05:30"}
    cutoff = "2025-03-22T14:00:00Z"
    assert nomination_eligible(record, cutoff)
    assert not nomination_eligible({**record, "modified_at": "2025-03-22T14:01:00Z"}, cutoff)
    assert not nomination_eligible({**record, "published_at": cutoff}, cutoff)
    assert not nomination_eligible({**record, "status": "reconstructed"}, cutoff)
    with pytest.raises(ValueError, match="time zones"):
        nomination_eligible({**record, "published_at": "2025-03-22T13:00:00"}, cutoff)


def test_machine_checked_records_require_explicit_opt_in_and_all_checks():
    record = {
        "status": "timestamped_report_machine_checked",
        "published_at": "2025-03-22T19:23:26+05:30",
        "checks": {},
    }
    cutoff = "2025-03-22T14:00:00Z"
    assert not nomination_eligible(record, cutoff, allow_machine_checked=True)
    record["checks"] = {
        key: True
        for key in (
            "known_unique_identities",
            "complete_membership",
            "no_known_team_membership_conflict",
            "independent_fixture_match",
            "original_starter_agreement_or_substitute_disjointness",
            "declared_timestamps_before_scheduled_start",
            "published_within_declared_one_hour_window",
        )
    }
    assert not nomination_eligible(record, cutoff)
    assert nomination_eligible(record, cutoff, allow_machine_checked=True)


def test_microdata_uses_entry_timestamp_not_page_update_or_in_play_mentions():
    html = """<div itemprop="liveBlogUpdate"><time itemprop="datePublished" datetime="2025-03-22T19:23:26+05:30"></time><meta itemprop="dateModified" content="2025-03-22T19:23:26+05:30"><meta itemprop="headline" content="Playing XIs"><meta itemprop="articleBody" content="CSK XI: A, B, C"></div>"""
    result = candidates_from_html(html, "https://example.test")
    assert len(result) == 1 and result[0]["published_at"] == "2025-03-22T19:23:26+05:30"
    assert result[0]["text"] == "CSK XI: A, B, C"
    assert not candidates_from_html(
        html.replace("Playing XIs", "Predicted Playing XIs"), "https://example.test"
    )
    assert not candidates_from_html(
        '<script type="application/ld+json">{"name":["not a string"]}</script>',
        "https://example.test",
    )


def test_team_specific_header_and_sub_options_segments_are_not_guessed_from_winner():
    names = {"CSK": "CSK", "MI": "MI", "Chennai": "CSK"}
    assert list(segments({"title": "CSK vs MI: Chennai playing XI", "text": "A, B, C"}, names)) == [
        ("CSK", "starting_xi", ["A", "B", "C"])
    ]
    result = list(
        segments(
            {"title": "Playing XIs", "text": "CSK XI: A, B MI Impact Sub options: C, D"}, names
        )
    )
    assert result == [
        ("CSK", "starting_xi", ["A", "B"]),
        ("MI", "nominated_substitutes", ["C", "D"]),
    ]


def test_reader_never_fills_missing_lineups_from_reconstructed_starters():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    insert_dict(
        db,
        "pilot_matches",
        {
            "pilot_match_id": "m",
            "match_id": "1",
            "official_gid": "gid",
            "match_date": "2025-03-22",
            "start_at": "2025-03-22T14:00:00Z",
            "team1_id": "CSK",
            "team2_id": "MI",
            "stage": "",
            "fixture_json": "{}",
        },
    )
    for team in ("CSK", "MI"):
        for kind in ("starting_xi", "nominated_substitutes"):
            insert_dict(
                db,
                "nominations",
                {
                    "pilot_match_id": "m",
                    "team_id": team,
                    "kind": kind,
                    "status": "unknown_unverified",
                    "published_at": None,
                    "player_ids_json": "[]",
                    "source_url": None,
                    "evidence_json": "{}",
                },
            )
    insert_dict(
        db,
        "player_form_snapshots",
        {
            "pilot_match_id": "m",
            "team_id": "CSK",
            "player_id": "p",
            "selection_basis": "reconstructed_conditional_not_strict",
            "form_json": "{}",
            "availability_json": "{}",
        },
    )
    for allow in (False, True):
        result = match_day_inputs(db, "m", allow_machine_checked=allow)
        assert result["lineup_features_complete"] is False
        assert all(not t["player_features"] for t in result["teams"])
        assert result["accuracy_target_validated"] is False
    db.close()


def test_annotations_and_oxford_commas_do_not_split_player_identities():
    assert names_in_list("A (C AND WK), B (On debut, in for X), C, and D.") == ["A", "B", "C", "D"]
    # A genuinely empty name remains a validation failure, rather than being
    # removed to manufacture an apparently complete list.
    assert names_in_list("A, , B") == ["A", "", "B"]


def test_combined_entries_keep_starting_xi_and_bench_membership_separate():
    candidate = {
        "title": "Playing XIs and Impact Subs",
        "text": "CSK: A, B\nImpact Subs: C, D\nMI: E, F Impact Subs: G, H",
    }
    assert list(segments(candidate, {"CSK": "CSK", "MI": "MI"})) == [
        ("CSK", "starting_xi", ["A", "B"]),
        ("CSK", "nominated_substitutes", ["C", "D"]),
        ("MI", "starting_xi", ["E", "F"]),
        ("MI", "nominated_substitutes", ["G", "H"]),
    ]


def test_explicit_nominated_players_and_dashed_xi_headers_are_recognized():
    teams = {"Gujarat Titans": "GT", "GT": "GT"}
    assert list(
        segments({"title": "", "text": "Impact players nominated by GT - A, B, and C."}, teams)
    ) == [("GT", "nominated_substitutes", ["A", "B", "C"])]
    assert list(
        segments({"title": "", "text": "Gujarat Titans (Unchanged Playing XI) - A (C), B."}, teams)
    ) == [("GT", "starting_xi", ["A", "B"])]


def test_projected_impact_choice_does_not_erase_the_next_confirmed_team():
    teams = {"KKR": "KKR", "Lucknow Super Giants": "LSG"}
    text = "KKR XI: A, B\nLikely impact player: ZLucknow Super Giants XI: C, D\nPossible impact: Y"
    reported = without_projected_choices(text, teams)
    assert list(segments({"title": "Playing XIs", "text": reported}, teams)) == [
        ("KKR", "starting_xi", ["A", "B"]),
        ("LSG", "starting_xi", ["C", "D"]),
    ]
    assert "likely XI" in without_projected_choices("Our likely XI is A, B", teams)


def test_public_pagination_parses_data_without_executing_callbacks():
    html = '<div itemprop="liveBlogUpdate"><time itemprop="datePublished" datetime="2025-06-03T19:12:49+05:30"></time><meta itemprop="dateModified" content="2025-06-03T19:12:49+05:30"><meta itemprop="headline" content="Impact Subs"><meta itemprop="articleBody" content="GT Impact Subs: A, B"></div>'
    records = candidates_from_html(
        "iplResearch(" + json.dumps({"comments": html}) + ")", "https://example.test"
    )
    assert len(records) == 1 and records[0]["published_at"] == "2025-06-03T19:12:49+05:30"
    with pytest.raises(ValueError, match="payload"):
        candidates_from_html('iplResearch({"comments":42})', "https://example.test")


def test_archive_links_stay_within_the_selected_public_article_and_page_bound():
    url = "https://timesofindia.indiatimes.com/sports/cricket/liveblog/123.cms"
    html = "".join(
        '<a href="' + x + '">next</a>'
        for x in [
            url + "?curpg=2",
            url + "?curpg=99",
            url.replace("123", "456") + "?curpg=2",
            "https://example.test/liveblog/123.cms?curpg=2",
            "http://timesofindia.indiatimes.com/sports/cricket/liveblog/123.cms?curpg=2",
        ]
    )
    assert archive_links(html, url) == [url + "?curpg=2"]


def test_public_commentary_uses_only_the_selected_match_prematch_entries():
    entry = {
        "commText": "B0$ A, B",
        "timestamp": 1748950200000,
        "commentaryFormats": {"bold": {"formatId": ["B0$"], "formatValue": ["GT Impact Subs:"]}},
    }
    data = {
        "matchPreviewFullComm": {
            "matchId": 7,
            "commentary": [
                {"inningsId": 0, "commentaryList": [entry]},
                {"inningsId": 1, "commentaryList": [entry]},
            ],
        }
    }
    html = "<script>self.__next_f.push(" + json.dumps([1, "21:" + json.dumps(data)]) + ")</script>"
    records = candidates_from_html(
        html, "https://www.cricbuzz.com/live-cricket-full-commentary/7/example"
    )
    assert len(records) == 1 and records[0]["text"] == "GT Impact Subs: A, B"
    assert (
        records[0]["modified_at"] is None
        and records[0]["modification_timestamp_available"] is False
    )
    assert records[0]["published_at"].endswith("+00:00")
    assert not candidates_from_html(
        html, "https://www.cricbuzz.com/live-cricket-full-commentary/8/other"
    )


def test_source_review_digest_changes_when_nomination_evidence_changes():
    record = {
        "match_id": "1",
        "team_id": "GT",
        "kind": "starting_xi",
        "names": ["A"],
        "player_ids": ["a"],
        "published_at": "2025-04-09T13:45:00+00:00",
        "source_url": "https://example.test/report",
    }
    original = nomination_review_digest(record)
    for key, value in [
        ("names", ["B"]),
        ("team_id", "RR"),
        ("published_at", "2025-04-09T14:15:00+00:00"),
        ("source_url", "https://example.test/other"),
    ]:
        assert nomination_review_digest(record | {key: value}) != original


def test_disjoint_opponent_bench_is_rejected_by_team_consistency_check():
    starters = {"own_starter"}
    bench = ["opponent_player", "unknown_player"]
    assert not starters.intersection(bench)
    assert team_membership_conflicts(bench, "PBKS", {"opponent_player": {"KKR"}}) == [
        "opponent_player"
    ]
    assert not team_membership_conflicts(
        ["own_player", "unknown_player"], "PBKS", {"own_player": {"PBKS"}}
    )
