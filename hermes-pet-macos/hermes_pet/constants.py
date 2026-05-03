"""Minimal path helpers for the standalone Hermes Pet package."""

from __future__ import annotations

import os
from pathlib import Path


def get_hermes_home() -> Path:
    value = os.environ.get("HERMES_HOME", "").strip()
    return Path(value) if value else Path.home() / ".hermes"


def get_default_hermes_root() -> Path:
    home = get_hermes_home()
    if home.parent.name == "profiles":
        return home.parent.parent
    if "HERMES_HOME" in os.environ:
        return home
    return Path.home() / ".hermes"
