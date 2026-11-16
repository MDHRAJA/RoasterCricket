"""Explicit research CLI; does not promote the challenger into live planning."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import Settings  # noqa: E402
from backend.database import connection  # noqa: E402
from backend.prematch_features import MatchContext  # noqa: E402
from backend.winner_forecast import forecast  # noqa: E402
from backend.winner_model import load_json_model  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batting-first", required=True)
    parser.add_argument("--chasing", required=True)
    parser.add_argument("--toss-winner", required=True)
    parser.add_argument("--venue", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--knockout", action="store_true")
    parser.add_argument("--first-xi", nargs=11)
    parser.add_argument("--chase-xi", nargs=11)
    args = parser.parse_args()
    settings = Settings(Settings.from_env().data_dir, query_timeout_seconds=30)
    model = load_json_model(ROOT / "outputs/match-winner-model.json")
    with settings.database.open("rb") as handle:
        if hashlib.file_digest(handle, "sha256").hexdigest() != model["database_sha256"]:
            raise ValueError("Model/data snapshot mismatch; rerun the research workflow")
    context = MatchContext(
        "user-supplied-hypothetical",
        args.as_of,
        int(args.as_of[:4]),
        args.venue,
        args.batting_first,
        args.chasing,
        args.toss_winner,
        "knockout" if args.knockout else "",
        tuple(sorted(args.first_xi)) if args.first_xi else None,
        tuple(sorted(args.chase_xi)) if args.chase_xi else None,
    )
    with connection(settings) as db:
        result = forecast(db, model, context)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
