"""Configuration independent of the current working directory."""

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://localhost:3000")
    query_timeout_seconds: float = 5.0

    def __post_init__(self):
        object.__setattr__(self, "data_dir", self.data_dir.resolve())
        if not 0 < self.query_timeout_seconds <= 30:
            raise ValueError("IPL_QUERY_TIMEOUT_SECONDS must be greater than 0 and at most 30")
        if "*" in self.cors_origins:
            raise ValueError("Use explicit frontend origins, not a wildcard")

    @property
    def database(self) -> Path:
        return self.data_dir / "ipl.sqlite"

    @classmethod
    def from_env(cls):
        directory = Path(os.environ.get("IPL_DATA_DIR", "outputs/ipl-data"))
        if not directory.is_absolute():
            directory = PROJECT_ROOT / directory
        origins = tuple(
            origin.strip()
            for origin in os.environ.get(
                "IPL_CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"
            ).split(",")
            if origin.strip()
        )
        return cls(directory, origins, float(os.environ.get("IPL_QUERY_TIMEOUT_SECONDS", "5")))
