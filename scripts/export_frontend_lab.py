"""Export public roster proxies and a paired real optimization example, read-only."""

import hashlib
import json
from pathlib import Path

from backend.config import Settings
from backend.database import connection, load_snapshot
from backend.match_models import OptimizationRequest, OptimizationResult
from backend.services import AnalyticsService

ROOT = Path(__file__).resolve().parents[1]
TEAM_IDS = ("CSK", "DC", "GT", "KKR", "LSG", "MI", "PBKS", "RR", "RCB", "SRH")
FIELDS = ("player_id", "display_name", "country", "primary_role", "is_wicketkeeper", "is_overseas")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    settings = Settings.from_env()
    before = digest(settings.database)
    snapshot = load_snapshot(settings)
    rosters = {}
    with connection(settings) as db:
        service = AnalyticsService(db, settings, snapshot)
        for team_id in TEAM_IDS:
            roster, warnings = service.roster(team_id, 2026)
            rosters[team_id] = {
                "team_id": team_id,
                "members": [{
                    "player": {key: member["player"].get(key) for key in FIELDS},
                    "availability": {key: member["availability"].get(key) for key in ("status", "effective_on")},
                } for member in roster["members"]],
                "warnings": warnings,
            }
        venues = service.rows("SELECT venue_id,display_name,city FROM venues ORDER BY display_name")
    request_path = ROOT / "outputs/xi-optimization-request.json"
    response_path = ROOT / "outputs/xi-optimization-example.json"
    request = OptimizationRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    response = json.loads(response_path.read_text(encoding="utf-8"))
    result = OptimizationResult.model_validate(response["data"])
    assert result.recommended["plan"]["team_id"] == request.team_id
    assert result.confirmation["simulations"] == request.simulations
    assert result.confirmation["training"]["exclusive_cutoff"] == request.as_of.isoformat()
    data = {
        "season": 2026, "dataset_version": snapshot["version"],
        "source_database_sha256": before, "rosters": rosters, "venues": venues,
        "optimizer_example": {
            "request": request.model_dump(mode="json"), "response": response,
            "provenance": {
                "request_source": request_path.relative_to(ROOT).as_posix(),
                "response_source": response_path.relative_to(ROOT).as_posix(),
                "request_sha256": digest(request_path), "response_sha256": digest(response_path),
            },
        },
    }
    assert digest(settings.database) == before
    target = ROOT / "frontend/src/api/snapshots/lab.json"
    target.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Saved {len(rosters)} roster snapshots, {len(venues)} grounds and one real optimizer result")


if __name__ == "__main__":
    main()
