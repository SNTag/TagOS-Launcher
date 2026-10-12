"""Application configuration: persisted to the user's config directory.

On Windows the config lives in ``%APPDATA%\\TagOS Launcher\\config.json``.
Nested sections are merged key-by-key with the defaults, so a config written by
an older version still picks up any options added since.
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict

APP_DIR_NAME = "TagOS Launcher"

DEFAULT_CONFIG: Dict[str, Any] = {
    # Global key combination that opens the launcher (Qt "portable" text).
    "hotkey": "Ctrl+Alt+Space",
    # UI colour theme: "dark" or "light".
    "theme": "dark",
    # Maximum number of rows shown for any command.
    "max_results": 50,
    # Hide the launcher as soon as it loses focus (click elsewhere / alt-tab).
    "hide_on_focus_loss": True,
    # Pop a tray notification when the launcher starts.
    "notify_on_start": False,
    "windows": {
        # List windows on other virtual desktops below the current desktop's.
        "show_other_desktops": True,
        # With an empty query, preselect the window you were in *before* the
        # current one (like Alt+Tab), so Enter flips back to it.
        "preselect_previous": True,
        # Row colours for windows on other desktops, by desktop number
        # (Desktop 1 uses the first colour, and so on, wrapping around).
        "desktop_colors": [
            "#3b6ea5",
            "#8e5ba8",
            "#3f8f6b",
            "#b5763a",
            "#a8485a",
            "#4b8a9c",
            "#8a8a3a",
            "#6a5acd",
        ],
        # Windows to leave out: a process name (e.g. "TextInputHost.exe") or
        # any text contained in the window title.
        "exclude": ["TextInputHost.exe"],
    },
    "obsidian": {
        "enabled": True,
        # What you type to search bookmarks.
        "prefix": "obs:",
        # Folder of bookmark notes (e.g. <vault>\Snippets). Empty = auto-detect.
        "folder": "",
        # Also search sub-folders.
        "recursive": True,
        # Frontmatter fields. Each may list several names separated by commas;
        # the first one present wins (aliases are combined from all of them).
        "title_field": "title",
        "aliases_field": "aliases",
        "url_field": "source",
        # What to do with notes that have no URL: "obsidian" (still list them;
        # Enter opens the note in Obsidian) or "hide".
        "without_url": "obsidian",
    },
    # Simple "prefix -> URL" commands; {query} is replaced by what you type.
    "web_commands": [
        {"prefix": "g:", "name": "Google", "url": "https://www.google.com/search?q={query}"},
    ],
}


def config_dir() -> str:
    """Return (creating if needed) the directory that holds the config file."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def config_path() -> str:
    return os.path.join(config_dir(), "config.json")


def merge(defaults: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """Return *defaults* updated with *data*, recursing into nested dicts."""
    result = copy.deepcopy(defaults)
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> Dict[str, Any]:
    """Load the config, falling back to defaults for any missing keys."""
    path = config_path()
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return merge(DEFAULT_CONFIG, data)
        except (json.JSONDecodeError, OSError):
            # A corrupt config should not crash the app; fall back to defaults.
            pass
    return copy.deepcopy(DEFAULT_CONFIG)


def save_config(cfg: Dict[str, Any]) -> None:
    with open(config_path(), "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
