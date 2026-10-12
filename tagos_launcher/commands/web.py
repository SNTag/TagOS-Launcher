"""User-defined ``prefix: query`` -> URL commands (e.g. ``g:`` for Google)."""

from __future__ import annotations

from typing import Callable, List
from urllib.parse import quote_plus

from .base import Action, Command, Item


class WebCommand(Command):
    glyph = "🌐"

    def __init__(self, prefix: str, name: str, url: str, open_url: Callable[[str], None]) -> None:
        self.prefix = prefix
        self.name = name or prefix
        self.url = url
        self.open_url = open_url
        self.description = f"Search {self.name}"

    def build_url(self, text: str) -> str:
        return self.url.replace("{query}", quote_plus(text))

    def query(self, text: str) -> List[Item]:
        if not text.strip():
            return [Item(title=f"Search {self.name}…", subtitle="Type your search", glyph=self.glyph)]
        url = self.build_url(text.strip())
        return [Item(
            title=f"Search {self.name} for “{text.strip()}”",
            subtitle=url,
            glyph=self.glyph,
            actions=[Action("Open", lambda: self.open_url(url))],
            copy_text=url,
        )]
