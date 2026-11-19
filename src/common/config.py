"""Load project and registry configuration. UNSET values fail loudly."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
UNSET = "UNSET"


class ConfigError(RuntimeError):
    pass


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def project() -> dict:
    return load_yaml(ROOT / "configs" / "project.yaml")


def require(value, name: str):
    """Return value, or stop: a missing value is never replaced by a guess."""
    if value is None or value == UNSET or value == "":
        raise ConfigError(
            f"{name} is not set. Ask the project lead for it and record it in the "
            f"registry or configs/project.yaml. Do not guess."
        )
    return value


def database(db_id: str, registry_path: Path | None = None) -> dict:
    reg = load_yaml(registry_path or ROOT / "registry" / "databases.yaml")
    for entry in reg.get("databases", []):
        if entry.get("id") == db_id:
            return entry
    raise ConfigError(f"database '{db_id}' is not in registry/databases.yaml")
