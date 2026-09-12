"""User configuration and persistent settings for DiskTriage.

Stores user preferences (such as selected language) in %LOCALAPPDATA%\\DiskTriage\\config.json.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .i18n import normalize_language


def get_default_config_path() -> Path:
    """Return the default configuration file path in %LOCALAPPDATA%\\DiskTriage\\config.json."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base_dir = Path(local_app_data) / "DiskTriage"
    else:
        base_dir = Path.home() / ".disktriage"
    return base_dir / "config.json"


def load_config(config_file: Path | None = None) -> dict[str, Any]:
    """Load configuration from disk. Return empty dictionary if file does not exist or is invalid."""
    target = config_file or get_default_config_path()
    if not target.is_file():
        return {}

    try:
        content = target.read_text(encoding="utf-8")
        data = json.loads(content)
        if isinstance(data, dict):
            return data
        return {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(config: dict[str, Any], config_file: Path | None = None) -> bool:
    """Save configuration to disk atomically."""
    target = config_file or get_default_config_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False

    payload = json.dumps(config, indent=2, ensure_ascii=False)

    try:
        with tempfile.NamedTemporaryFile(
            "w",
            dir=target.parent,
            encoding="utf-8",
            delete=False,
            suffix=".tmp",
        ) as tmp:
            tmp.write(payload)
            tmp_path = Path(tmp.name)

        tmp_path.replace(target)
        return True
    except OSError:
        try:
            if "tmp_path" in locals() and tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        return False


def get_configured_language(config_file: Path | None = None) -> str | None:
    """Return the configured language code, or None if not set."""
    cfg = load_config(config_file)
    lang = cfg.get("language")
    if lang and isinstance(lang, str):
        return normalize_language(lang)
    return None


def set_configured_language(lang: str, config_file: Path | None = None) -> bool:
    """Persist the configured language to disk."""
    cfg = load_config(config_file)
    cfg["language"] = normalize_language(lang)
    return save_config(cfg, config_file)
