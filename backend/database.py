"""Read-only SQLite connections scoped to one request, never a global shared connection."""

import json
import sqlite3
import time
from contextlib import contextmanager

from backend.config import Settings

REQUIRED_TABLES = {
    "wickets",
    "players",
    "player_attributes",
    "player_aliases",
    "teams",
    "squads_current",
    "squads_historical_observed",
    "matches",
    "innings",
    "deliveries",
    "match_players",
    "replacements",
    "player_match_stats",
    "season_coverage",
    "venues",
    "venue_aliases",
}


@contextmanager
def connection(settings: Settings):
    db = sqlite3.connect(
        settings.database.as_uri() + "?mode=ro",
        uri=True,
        timeout=2,
        check_same_thread=False,
    )
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    deadline = time.monotonic() + settings.query_timeout_seconds
    db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
    try:
        yield db
    finally:
        db.close()


def load_snapshot(settings: Settings) -> dict:
    if not settings.database.is_file():
        raise RuntimeError(
            "IPL database is missing. Collect/build the dataset or set IPL_DATA_DIR."
        )
    try:
        catalog = json.loads((settings.data_dir / "dataset_catalog.json").read_text("utf-8"))
        coverage = json.loads((settings.data_dir / "coverage_summary.json").read_text("utf-8"))
        if not isinstance(catalog, list) or not catalog or not isinstance(coverage, dict):
            raise ValueError("Invalid metadata structure")
        versions = {item["as_of"] for item in catalog}
        schemas = {item["dataset"]: item["columns"] for item in catalog}
        if len(schemas) != len(catalog) or not REQUIRED_TABLES <= schemas.keys():
            raise ValueError("Incomplete or duplicate catalog schema")
        if any(
            not isinstance(cols, list) or not all(isinstance(c, str) for c in cols)
            for cols in schemas.values()
        ):
            raise ValueError("Invalid column metadata")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(
            "Required dataset catalog/coverage metadata is missing or invalid"
        ) from exc
    if len(versions) != 1:
        raise RuntimeError("The dataset catalog must identify one consistent snapshot date")
    with connection(settings) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if missing := REQUIRED_TABLES - tables:
            raise RuntimeError(f"IPL database schema is incomplete: {', '.join(sorted(missing))}")
        if db.execute("PRAGMA user_version").fetchone()[0] not in (0, 1):
            raise RuntimeError("Unsupported IPL database schema version")
        for table in sorted(REQUIRED_TABLES):
            # Table names are server-owned; no user-provided identifiers enter SQL.
            columns = {r[1] for r in db.execute(f"PRAGMA table_info({table})")}
            if missing := set(schemas[table]) - columns:
                raise RuntimeError(
                    f"IPL database columns are incomplete in {table}: {', '.join(sorted(missing))}"
                )
        seasons = [
            int(r[0]) for r in db.execute("SELECT season FROM season_coverage ORDER BY season")
        ]
        roster_seasons = [
            int(r[0]) for r in db.execute("SELECT DISTINCT season FROM squads_current")
        ]
    return {
        "version": versions.pop(),
        "catalog": catalog,
        "coverage": coverage,
        "seasons": seasons,
        "roster_seasons": roster_seasons,
    }
