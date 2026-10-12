"""Command registry: picks the command for the typed text."""

from __future__ import annotations

from typing import List, Tuple

from .base import Action, Command, Item

HELP_PREFIX = "?"


class HelpCommand(Command):
    name = "Help"
    prefix = HELP_PREFIX
    description = "List every command"
    glyph = "?"

    def __init__(self, registry: "CommandRegistry") -> None:
        self.registry = registry

    def query(self, text: str) -> List[Item]:
        items = []
        for cmd in self.registry.all_commands():
            if cmd is self:
                continue
            label = cmd.prefix or "(just type)"
            items.append(Item(
                title=f"{label}   {cmd.name}",
                subtitle=cmd.description,
                glyph=cmd.glyph,
                actions=[Action("Use", fill=cmd.prefix)],
            ))
        return items


class CommandRegistry:
    def __init__(self, default: Command, prefixed: List[Command]) -> None:
        self.default = default
        self.prefixed = [c for c in prefixed if c.prefix]
        self.prefixed.append(HelpCommand(self))
        # Longest prefix wins so "obsx:" can coexist with "obs:".
        self.prefixed.sort(key=lambda c: -len(c.prefix))

    def all_commands(self) -> List[Command]:
        return [self.default] + sorted(self.prefixed, key=lambda c: c.prefix)

    def resolve(self, text: str) -> Tuple[Command, str]:
        lowered = text.lower()
        for cmd in self.prefixed:
            if lowered.startswith(cmd.prefix.lower()):
                return cmd, text[len(cmd.prefix):].strip()
        return self.default, text

    def suggestions(self, text: str) -> List[Item]:
        """Commands whose prefix starts with *text* (offered under the default
        command's results, e.g. typing "ob" offers "obs:")."""
        stripped = text.strip().lower()
        if not stripped:
            return []
        out = []
        for cmd in sorted(self.prefixed, key=lambda c: c.prefix):
            if cmd.prefix.lower().startswith(stripped) and cmd.prefix != HELP_PREFIX:
                out.append(Item(
                    title=f"{cmd.prefix}  {cmd.name}",
                    subtitle=cmd.description + "  (Tab)",
                    glyph=cmd.glyph,
                    actions=[Action("Use", fill=cmd.prefix)],
                ))
        return out

    def on_open(self) -> None:
        for cmd in self.all_commands():
            cmd.on_open()


__all__ = ["Action", "Command", "CommandRegistry", "Item"]
