"""Building blocks for launcher commands.

A *command* turns the text you type into a list of :class:`Item` rows. Each row
carries up to three :class:`Action` s, bound to Enter, Shift+Enter and
Ctrl+Enter respectively. Commands are selected by prefix (``obs:``, ``g:``);
the command with an empty prefix handles everything else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional


@dataclass
class Action:
    label: str
    callback: Optional[Callable[[], None]] = None
    # If set, the action replaces the input text instead of running anything
    # (used to drill into another command, e.g. "obs:").
    fill: Optional[str] = None


@dataclass
class Item:
    title: str
    subtitle: str = ""
    # Short text drawn on the right of the row (e.g. a desktop name).
    badge: str = ""
    # Row tint (hex colour); None for the default background.
    color: Optional[str] = None
    # A file whose icon represents the row (e.g. a window's .exe) ...
    icon_path: str = ""
    # ... or a single character/emoji drawn instead.
    glyph: str = ""
    # Slot 0 = Enter, 1 = Shift+Enter, 2 = Ctrl+Enter; None leaves a slot empty
    # so a key keeps the same meaning across rows.
    actions: List[Optional[Action]] = field(default_factory=list)
    # Text placed on the clipboard by Ctrl+C.
    copy_text: str = ""
    # Command-specific payload.
    data: Any = None


class Command:
    #: Human-readable name, shown in help.
    name = ""
    #: Text that selects this command ("" = the default command).
    prefix = ""
    description = ""
    glyph = ""

    def on_open(self) -> None:
        """Called each time the launcher opens (take snapshots here)."""

    def query(self, text: str) -> List[Item]:
        raise NotImplementedError

    def initial_index(self, text: str, items: List[Item]) -> int:
        """Row to preselect for *items*."""
        return 0
