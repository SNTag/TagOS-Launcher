"""Index a folder of Obsidian bookmark notes by their YAML frontmatter.

A bookmark is any Markdown note whose frontmatter names a title, optional
aliases and a URL, e.g.::

    ---
    title: Python asyncio docs
    aliases: [asyncio, event loop]
    source: https://docs.python.org/3/library/asyncio.html
    ---

Which frontmatter fields hold the title / aliases / URL is configurable. Notes
are re-read only when their modification time changes, so refreshing the index
each time the launcher opens is cheap.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import yaml

from .matching import score

# Only the start of each note is read: frontmatter always sits at the top.
_HEAD_BYTES = 64 * 1024

# Folder names tried (in each Obsidian vault) when no folder is configured.
GUESS_FOLDER_NAMES = ("Snippets", "snippets", "Bookmarks", "bookmarks", "Clippings")


@dataclass
class Bookmark:
    path: str
    title: str
    aliases: List[str] = field(default_factory=list)
    url: str = ""
    mtime: float = 0.0


def parse_frontmatter(text: str) -> Dict[str, Any]:
    """Return the note's YAML frontmatter as a dict ({} if there is none)."""
    if not text.startswith("---"):
        return {}
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return {}
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            try:
                data = yaml.safe_load("\n".join(lines[1:i]))
            except yaml.YAMLError:
                return {}
            return data if isinstance(data, dict) else {}
    return {}


def field_names(spec: str) -> List[str]:
    """Split a configured field spec ("aliases, alias") into names."""
    return [name.strip() for name in str(spec or "").split(",") if name.strip()]


def _lookup(meta: Dict[str, Any], name: str) -> Any:
    """Case-insensitive frontmatter lookup."""
    if name in meta:
        return meta[name]
    lowered = name.lower()
    for key, value in meta.items():
        if str(key).lower() == lowered:
            return value
    return None


def _as_strings(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    text = str(value).strip()
    return [text] if text else []


def bookmark_from_meta(
    path: str,
    meta: Dict[str, Any],
    title_field: str = "title",
    aliases_field: str = "aliases",
    url_field: str = "source",
    mtime: float = 0.0,
) -> Bookmark:
    title = ""
    for name in field_names(title_field):
        values = _as_strings(_lookup(meta, name))
        if values:
            title = values[0]
            break
    if not title:
        title = os.path.splitext(os.path.basename(path))[0]

    aliases: List[str] = []
    for name in field_names(aliases_field):
        for alias in _as_strings(_lookup(meta, name)):
            if alias not in aliases and alias != title:
                aliases.append(alias)

    url = ""
    for name in field_names(url_field):
        values = _as_strings(_lookup(meta, name))
        if values:
            url = values[0]
            break
    return Bookmark(path=path, title=title, aliases=aliases, url=url, mtime=mtime)


def read_bookmark(path: str, title_field: str, aliases_field: str, url_field: str) -> Optional[Bookmark]:
    try:
        mtime = os.path.getmtime(path)
        with open(path, "r", encoding="utf-8-sig", errors="replace") as fh:
            head = fh.read(_HEAD_BYTES)
    except OSError:
        return None
    meta = parse_frontmatter(head)
    return bookmark_from_meta(path, meta, title_field, aliases_field, url_field, mtime)


def obsidian_uri(path: str) -> str:
    """URI that opens *path* in Obsidian (the note's vault must be registered)."""
    return "obsidian://open?path=" + quote(os.path.abspath(path), safe="")


class BookmarkIndex:
    """In-memory, incrementally refreshed index of a bookmarks folder."""

    def __init__(
        self,
        folder: str = "",
        title_field: str = "title",
        aliases_field: str = "aliases",
        url_field: str = "source",
        recursive: bool = True,
    ) -> None:
        self.folder = folder
        self.title_field = title_field
        self.aliases_field = aliases_field
        self.url_field = url_field
        self.recursive = recursive
        self._cache: Dict[str, Bookmark] = {}

    @property
    def bookmarks(self) -> List[Bookmark]:
        return list(self._cache.values())

    def clear(self) -> None:
        self._cache.clear()

    def _note_paths(self) -> List[Tuple[str, float]]:
        found: List[Tuple[str, float]] = []
        if not self.folder or not os.path.isdir(self.folder):
            return found
        stack = [self.folder]
        while stack:
            current = stack.pop()
            try:
                entries = list(os.scandir(current))
            except OSError:
                continue
            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        # Skip Obsidian's own config and other dot-folders.
                        if self.recursive and not entry.name.startswith("."):
                            stack.append(entry.path)
                    elif entry.name.lower().endswith(".md"):
                        found.append((entry.path, entry.stat().st_mtime))
                except OSError:
                    continue
        return found

    def refresh(self) -> None:
        """Pick up new, changed and deleted notes."""
        seen = set()
        for path, mtime in self._note_paths():
            seen.add(path)
            cached = self._cache.get(path)
            if cached is not None and cached.mtime == mtime:
                continue
            bookmark = read_bookmark(path, self.title_field, self.aliases_field, self.url_field)
            if bookmark is not None:
                self._cache[path] = bookmark
        for path in list(self._cache):
            if path not in seen:
                del self._cache[path]

    def search(self, query: str, limit: int = 50) -> List[Tuple[Bookmark, Optional[str]]]:
        """Return ``(bookmark, matched_alias)`` pairs, best first.

        ``matched_alias`` is the alias that matched when it beat the title (so
        the UI can show why a result appeared). An empty query lists the most
        recently modified bookmarks.
        """
        if not query.strip():
            recent = sorted(self._cache.values(), key=lambda b: b.mtime, reverse=True)
            return [(b, None) for b in recent[:limit]]
        scored = []
        for bm in self._cache.values():
            best = score(query, bm.title)
            via: Optional[str] = None
            for alias in bm.aliases:
                s = score(query, alias)
                if s is not None and (best is None or s > best):
                    best, via = s, alias
            if best is not None:
                scored.append((best, bm, via))
        scored.sort(key=lambda t: (-t[0], t[1].title.lower()))
        return [(bm, via) for _, bm, via in scored[:limit]]


# ------------------------------------------------------------ vault discovery
def obsidian_config_file() -> str:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "obsidian", "obsidian.json")


def find_vaults() -> List[str]:
    """Vault folders Obsidian knows about (most recently opened first)."""
    try:
        with open(obsidian_config_file(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    vaults = data.get("vaults") if isinstance(data, dict) else None
    if not isinstance(vaults, dict):
        return []
    entries = [v for v in vaults.values() if isinstance(v, dict) and v.get("path")]
    entries.sort(key=lambda v: v.get("ts", 0), reverse=True)
    return [v["path"] for v in entries if os.path.isdir(v["path"])]


def guess_bookmarks_folder() -> str:
    """Best guess at the bookmarks folder: a well-known name inside a vault."""
    for vault in find_vaults():
        for name in GUESS_FOLDER_NAMES:
            candidate = os.path.join(vault, name)
            if os.path.isdir(candidate):
                return candidate
    return ""
