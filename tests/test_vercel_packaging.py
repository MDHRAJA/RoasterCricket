"""Deployment packaging must not leak local files or accept a damaged snapshot."""

import json
import shutil
import sys
import tomllib
from pathlib import Path

import pytest

from scripts.check_vercel_backend import check
from scripts.stage_vercel_backend import CONFIG_FILES, stage


def test_cloud_and_local_runtime_pins_match():
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text("utf-8"))
    pins = {
        line.strip()
        for line in (root / "requirements-backend.txt").read_text("utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert set(project["project"]["dependencies"]) == pins


@pytest.fixture
def export_root(tmp_path, data_dir):
    root = tmp_path / "project"
    for name in CONFIG_FILES:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture\n", encoding="utf-8")
    (root / "backend").mkdir()
    (root / "backend/main.py").write_text("# fixture\n", encoding="utf-8")
    shutil.copytree(data_dir, root / "outputs/ipl-data")
    for name in (".env", "tests/private.txt", "outputs/ipl-data/raw/private.txt"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("MUST NOT UPLOAD", encoding="utf-8")
    return root


def test_stage_is_an_allowlist_and_preserves_dataset(export_root):
    output = export_root / "work/backend"
    stage(output, export_root)
    assert not (output / ".env").exists()
    assert not (output / "tests").exists()
    assert not (output / "outputs/ipl-data/raw").exists()
    assert (output / "outputs/ipl-data/ipl.sqlite").read_bytes() == (
        export_root / "outputs/ipl-data/ipl.sqlite"
    ).read_bytes()
    assert not (export_root / "runtime-manifest.json").exists()


def test_platform_config_normalization_does_not_break_data_receipts(export_root, monkeypatch):
    output = export_root / "work/backend"
    stage(output, export_root)
    (output / "vercel.json").write_text('{"platform": "normalized"}', encoding="utf-8")
    monkeypatch.setenv("IPL_DATA_DIR", str(output / "outputs/ipl-data"))
    monkeypatch.setattr(sys, "path", sys.path.copy())
    assert check(output)["status"] == "ready"


def test_stage_never_replaces_existing_deployment_or_writes_outside_work(export_root):
    output = export_root / "work/backend"
    stage(output, export_root)
    marker = output / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        stage(output, export_root)
    assert marker.read_text() == "keep"
    with pytest.raises(ValueError, match="inside"):
        stage(export_root / "public", export_root)
    assert not (export_root / "public").exists()


def test_stage_refuses_missing_database_before_copying(export_root):
    (export_root / "outputs/ipl-data/ipl.sqlite").unlink()
    output = export_root / "work/backend"
    with pytest.raises(ValueError, match="missing"):
        stage(output, export_root)
    assert not output.exists()


def test_check_validates_real_schema_and_detects_same_size_corruption(export_root, monkeypatch):
    output = export_root / "work/backend"
    stage(output, export_root)
    monkeypatch.setenv("IPL_DATA_DIR", str(output / "outputs/ipl-data"))
    monkeypatch.setattr(sys, "path", sys.path.copy())
    assert check(output)["status"] == "ready"
    database = output / "outputs/ipl-data/ipl.sqlite"
    contents = database.read_bytes()
    database.write_bytes(b"X" + contents[1:])
    with pytest.raises(ValueError, match="checksum"):
        check(output)


@pytest.mark.parametrize("relative", ["../outside.txt", "outputs/ipl-data/ipl.sqlite"])
def test_check_refuses_traversal_and_duplicate_receipts(export_root, relative):
    output = export_root / "work/backend"
    stage(output, export_root)
    path = output / "runtime-manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest["files"].append({"path": relative, "bytes": 0, "sha256": ""})
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid or duplicate"):
        check(output)
