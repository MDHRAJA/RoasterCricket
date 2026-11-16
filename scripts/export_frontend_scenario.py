"""Package an attributable, real saved run for the local Match preview."""

import hashlib
import json
import sqlite3
from pathlib import Path

from backend.match_models import SimulationRequest, SimulationResult

ROOT = Path(__file__).resolve().parents[1]


def main():
    request_path = ROOT / "outputs/match-simulation-request.json"
    result_path = ROOT / "outputs/match-simulation-example.json"
    request = SimulationRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    envelope = json.loads(result_path.read_text(encoding="utf-8"))
    result = SimulationResult.model_validate(envelope["data"])
    assert result.seed == request.seed and result.simulations == request.simulations
    assert result.training["exclusive_cutoff"] == request.as_of.isoformat()
    ids = {p for plan in (request.team_a, request.team_b) for p in plan.starting_xi}
    db = sqlite3.connect((ROOT / "outputs/ipl-data/ipl.sqlite").as_uri() + "?mode=ro", uri=True)
    names = dict(db.execute(
        "SELECT player_id,display_name FROM players WHERE player_id IN ("
        + ",".join("?" for _ in ids) + ")", sorted(ids)
    ))
    venue = db.execute("SELECT display_name,city FROM venues WHERE venue_id=?", (request.venue_id,)).fetchone()
    db.close()
    assert set(names) == ids and venue
    data = {
        "id": "scenario-csk-mi", "label": "CSK v MI / saved planning example",
        "request": request.model_dump(mode="json"), "response": envelope,
        "players": names, "venue": {"name": venue[0], "city": venue[1]},
        "provenance": {
            "request_source": request_path.relative_to(ROOT).as_posix(),
            "request_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest(),
            "response_source": result_path.relative_to(ROOT).as_posix(),
            "response_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
            "kind": "saved_project_run_not_a_historical_prediction_or_scheduled_fixture",
        },
    }
    target = ROOT / "frontend/src/api/snapshots/scenario-csk-mi.json"
    target.write_text(json.dumps(data, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Saved {result.simulations} trials, {len(names)} public player labels and sample delivery events")


if __name__ == "__main__":
    main()
