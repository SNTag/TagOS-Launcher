"""``obs:`` — search Obsidian bookmark notes by title or alias, open their URL."""

from __future__ import annotations

from typing import Any, Callable, Dict, List
from urllib.parse import urlparse

from ..obsidian import BookmarkIndex, obsidian_uri
from .base import Action, Command, Item

OpenUrl = Callable[[str], None]


class ObsidianBookmarksCommand(Command):
    name = "Obsidian bookmarks"
    description = "Search bookmark notes by title or alias; Enter opens the source URL"
    glyph = "🔖"

    def __init__(self, config: Dict[str, Any], index: BookmarkIndex, open_url: OpenUrl, max_results: int = 50) -> None:
        self.config = config
        self.index = index
        self.open_url = open_url
        self.max_results = max_results
        self.prefix = config.get("prefix") or "obs:"

    def on_open(self) -> None:
        self.index.refresh()

    def query(self, text: str) -> List[Item]:
        if not self.index.folder:
            return [Item(
                title="No bookmarks folder set",
                subtitle="Open Settings → Obsidian to choose the folder that holds your bookmark notes",
                glyph="⚠",
            )]
        hide_without_url = self.config.get("without_url") == "hide"
        items: List[Item] = []
        for bm, via in self.index.search(text, limit=self.max_results * 2):
            if not bm.url and hide_without_url:
                continue
            note_uri = obsidian_uri(bm.path)
            parts = []
            if via:
                parts.append(f"alias: {via}")
            elif bm.aliases:
                parts.append(", ".join(bm.aliases[:3]))
            parts.append(bm.url or "no URL — opens the note")
            actions: List[Action] = []
            if bm.url:
                actions.append(Action("Open link", lambda u=bm.url: self.open_url(u)))
            actions.append(Action("Open note in Obsidian", lambda u=note_uri: self.open_url(u)))
            items.append(Item(
                title=bm.title,
                subtitle="  ·  ".join(parts),
                badge=urlparse(bm.url).netloc if bm.url else "",
                glyph=self.glyph,
                actions=actions,
                copy_text=bm.url or note_uri,
                data=bm,
            ))
            if len(items) >= self.max_results:
                break
        if not items:
            items.append(Item(title="No matching bookmarks", subtitle=self.index.folder, glyph="∅"))
        return items
