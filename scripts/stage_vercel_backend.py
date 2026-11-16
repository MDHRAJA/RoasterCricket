"""Stage only runtime source/data for a Vercel CLI upload; never publish a data mirror."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_FILES = (
    "ipl.sqlite",
    "dataset_catalog.json",
    "coverage_summary.json",
)
CONFIG_FILES = (
    "pyproject.toml",
    "requirements.txt",
    "requirements-backend.txt",
    ".python-version",
    "vercel.json",
    "scripts/check_vercel_backend.py",
)


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def stage(output: Path, root: Path = ROOT):
    root, output = root.resolve(), output.resolve()
    staging_root = root / "work"
    if not output.is_relative_to(staging_root) or output == staging_root:
        raise ValueError("Choose an output directory inside this project's work/ folder")
    if output.exists() and any(output.iterdir()):
        raise ValueError(
            "Output must be empty; choose a new directory to preserve prior deployments"
        )
    sources = [(root / name, name) for name in CONFIG_FILES]
    sources += [
        (path, path.relative_to(root).as_posix()) for path in (root / "backend").glob("*.py")
    ]
    data = root / "outputs/ipl-data"
    sources += [(data / name, f"outputs/ipl-data/{name}") for name in DATA_FILES]
    if (data / "manual/availability.csv").is_file():
        sources.append(
            (data / "manual/availability.csv", "outputs/ipl-data/manual/availability.csv")
        )
    for source, _ in sources:
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"Required runtime source is missing or a symlink: {source.name}")
    if not any(name == "backend/main.py" for _, name in sources):
        raise ValueError("Backend entrypoint is missing")
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for source, relative in sorted(sources, key=lambda entry: entry[1]):
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        # Vercel normalizes deployment configuration during the build. Receipt only
        # immutable runtime source/data, not configuration managed by the platform.
        if relative not in CONFIG_FILES or relative == "scripts/check_vercel_backend.py":
            manifest.append(
                {"path": relative, "bytes": target.stat().st_size, "sha256": digest(target)}
            )
    (output / "runtime-manifest.json").write_text(
        json.dumps({"format": 1, "files": manifest}, indent=2) + "\n", encoding="utf-8"
    )
    (output / ".vercelignore").write_text(
        ".vercel/\n__pycache__/\n**/__pycache__/\n*.pyc\n.env\n.env.*\n", encoding="utf-8"
    )
    return {
        "directory": str(output),
        "files": len(sources),
        "bytes": sum(source.stat().st_size for source, _ in sources),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "work/vercel/backend")
    args = parser.parse_args()
    try:
        print(json.dumps(stage(args.output), indent=2))
    except ValueError as exc:
        parser.exit(1, f"Cannot stage backend: {exc}\n")


if __name__ == "__main__":
    main()
