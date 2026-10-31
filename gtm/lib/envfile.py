"""Load KEY=VALUE files. Values stay in the process environment."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GTM_ROOT = REPO_ROOT / "gtm"


def load_env_file(path: Path) -> list[str]:
    """Set variables that are not already in the environment.

    Returns the names this file set. A name that is already set is left as-is.
    """
    if not path.is_file():
        return []
    set_names: list[str] = []
    text = path.read_text(encoding="utf-8")
    for line_number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            raise ValueError(f"{path}:{line_number} is not KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"{path}:{line_number} has an empty name")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key in os.environ:
            continue
        os.environ[key] = value
        set_names.append(key)
    return set_names


def load_default_env(env_file: Path | None) -> None:
    """Load --env-file, then gtm/.env, then .env.gtm. Existing vars win."""
    paths: list[Path] = []
    if env_file is not None:
        paths.append(env_file)
    paths.append(GTM_ROOT / ".env")
    paths.append(REPO_ROOT / ".env.gtm")
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        load_env_file(path)
