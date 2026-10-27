"""Filesystem path helpers for resolving repository roots and sample datasets.

Supports execution from repo root, backend subdirectory, Docker containers,
and tests regardless of current working directory.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_repo_root() -> Path:
    """Find the STARF repository root directory."""
    # 1. Environment variable override
    env_root = os.environ.get("STARF_REPO_ROOT")
    if env_root and Path(env_root).is_dir():
        return Path(env_root).resolve()

    # 2. Search upwards from current file for markers (config/rules.yaml or pyproject.toml)
    for p in Path(__file__).resolve().parents:
        if (p / "config" / "rules.yaml").is_file() or (p / "pyproject.toml").is_file():
            return p

    # 3. Search upwards from cwd
    for p in [Path.cwd()] + list(Path.cwd().parents):
        if (p / "config" / "rules.yaml").is_file() or (p / "pyproject.toml").is_file():
            return p

    # 4. Fallback: parents[3] of backend/app/core/paths.py
    return Path(__file__).resolve().parents[3]


def get_samples_dir() -> Path:
    """Locate the data/samples directory containing CAN-bus CSV datasets."""
    # 1. Environment variable override
    env_samples = os.environ.get("STARF_SAMPLES_DIR") or os.environ.get("SAMPLES_DIR")
    if env_samples and Path(env_samples).is_dir():
        return Path(env_samples).resolve()

    # 2. Relative to repo root
    root = get_repo_root()
    cand = root / "data" / "samples"
    if cand.is_dir():
        return cand

    # 3. Search upwards from cwd
    for p in [Path.cwd()] + list(Path.cwd().parents):
        cand = p / "data" / "samples"
        if cand.is_dir():
            return cand

    return cand


def get_rules_yaml() -> Path:
    """Locate the config/rules.yaml file."""
    env_rules = os.environ.get("STARF_RULES_YAML") or os.environ.get("RULES_YAML")
    if env_rules and Path(env_rules).is_file():
        return Path(env_rules).resolve()

    root = get_repo_root()
    cand = root / "config" / "rules.yaml"
    if cand.is_file():
        return cand

    for p in [Path.cwd()] + list(Path.cwd().parents):
        cand = p / "config" / "rules.yaml"
        if cand.is_file():
            return cand

    return cand
