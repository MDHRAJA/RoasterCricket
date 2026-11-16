"""Export strict and explicitly lower-tier source-checked feature JSONL side by side."""

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.match_day_inputs import match_day_inputs  # noqa: E402


def main():
    pack = ROOT / "outputs/prematch-2025"
    db = sqlite3.connect((pack / "prematch.sqlite").as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    ids = [
        r[0]
        for r in db.execute(
            "SELECT pilot_match_id FROM pilot_matches ORDER BY match_date,pilot_match_id"
        )
    ]
    totals = {}
    for filename, allow in (
        ("match_day_strict.jsonl", False),
        ("match_day_source_checked.jsonl", True),
    ):
        count = 0
        with (pack / filename).open("w", encoding="utf-8") as handle:
            for mid in ids:
                result = match_day_inputs(db, mid, allow_machine_checked=allow)
                count += int(result["lineup_features_complete"])
                handle.write(json.dumps(result, allow_nan=False) + "\n")
        totals[filename] = {
            "fixture_records": len(ids),
            "complete_lineups_and_substitute_lists": count,
        }
    db.close()
    (pack / "feature_export_coverage.json").write_text(
        json.dumps(totals, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(totals, indent=2))


if __name__ == "__main__":
    main()
