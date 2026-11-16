"""Fail the deployment build if its runtime snapshot is missing, changed or unusable."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(root=ROOT):
    root = root.resolve()
    manifest_path = root / "runtime-manifest.json"
    if not manifest_path.is_file():
        raise ValueError(
            "Runtime data is not in Git. Run scripts/stage_vercel_backend.py locally, "
            "then deploy its work/vercel/backend directory with Vercel CLI."
        )
    manifest = json.loads(manifest_path.read_text("utf-8"))
    if manifest.get("format") != 1 or not isinstance(manifest.get("files"), list):
        raise ValueError("Invalid runtime manifest")
    paths = set()
    for entry in manifest["files"]:
        relative = entry["path"]
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or relative in paths:
            raise ValueError("Invalid or duplicate manifest path")
        paths.add(relative)
        if not path.is_file() or path.stat().st_size != entry["bytes"]:
            raise ValueError(f"Runtime file is missing or its size changed: {relative}")
        with path.open("rb") as handle:
            actual = hashlib.file_digest(handle, "sha256").hexdigest()
        if actual != entry["sha256"]:
            raise ValueError(f"Runtime file checksum changed: {relative}")
    required = {
        "outputs/ipl-data/" + name
        for name in ("ipl.sqlite", "dataset_catalog.json", "coverage_summary.json")
    }
    if not required <= paths:
        raise ValueError("Runtime manifest is missing required dataset files")
    # Ensure imports resolve to the staged application, including when launched as a script.
    sys.path.insert(0, str(root))
    from backend.config import Settings
    from backend.database import connection, load_snapshot

    settings = Settings.from_env()
    expected = root / "outputs/ipl-data"
    if settings.data_dir != expected.resolve():
        raise ValueError("IPL_DATA_DIR must identify the packaged outputs/ipl-data snapshot")
    snapshot = load_snapshot(settings)
    with connection(settings) as db:
        integrity = db.execute("PRAGMA quick_check").fetchone()[0]
        if integrity != "ok":
            raise ValueError("SQLite integrity check failed")
        if db.execute("PRAGMA query_only").fetchone()[0] != 1:
            raise ValueError("Dataset connection must remain read-only")
    return {"status": "ready", "dataset_version": snapshot["version"], "verified_files": len(paths)}


if __name__ == "__main__":
    try:
        print(json.dumps(check(), indent=2))
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        raise SystemExit(f"Backend deployment check failed: {exc}") from None
