"""Shared utilities for sim layer."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def repo_root() -> Path:
    """Return absolute path to repository root."""
    return Path(__file__).resolve().parent.parent.parent


def load_config(name: str) -> dict[str, Any]:
    """Load a YAML config from configs/ by name (e.g. 'arena')."""
    path = repo_root() / "configs" / f"{name}.yaml"
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def asset_path(rel: str) -> str:
    """Return absolute path for a repo-relative asset path."""
    return str(repo_root() / rel)
