"""Default command: list open windows and switch between them.

Windows on the current virtual desktop come first (most recently used first).
Windows on other desktops follow, grouped by desktop and tinted with that
desktop's colour. Typing filters by window title (and process name).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .. import desktops, winapi
from ..matching import score
from .base import Action, Command, Item


class WindowsCommand(Command):
    name = "Windows"
    prefix = ""
    description = "Switch between open windows (just start typing)"
    glyph = "🗔"

    def __init__(self, config: Dict[str, Any], max_results: int = 50) -> None:
        self.config = config
        self.max_results = max_results
        self._windows: List[winapi.WindowInfo] = []
        self._desktops = desktops.DesktopInfo()
        self._foreground = 0

    # The launcher calls this *before* showing itself, so the foreground window
    # is still the one you were working in.
    def on_open(self) -> None:
        self._foreground = winapi.foreground_window()
        self._desktops = desktops.snapshot()
        self._windows = winapi.list_windows()
        if self._desktops.current_id is None:
            for w in self._windows:
                if w.on_current_desktop and w.desktop_id:
                    self._desktops.current_id = w.desktop_id
                    break

    def set_snapshot(self, windows: List[winapi.WindowInfo], info: desktops.DesktopInfo, foreground: int = 0) -> None:
        """Inject a snapshot (used by tests and the non-Windows preview)."""
        self._windows = windows
        self._desktops = info
        self._foreground = foreground

    def _excluded(self, w: winapi.WindowInfo) -> bool:
        title = w.title.lower()
        proc = w.process_name.lower()
        for rule in self.config.get("exclude", []) or []:
            rule = str(rule).strip().lower()
            if rule and (rule == proc or rule in title):
                return True
        return False

    def _color_for(self, desktop: Optional[desktops.Desktop]) -> Optional[str]:
        colors = self.config.get("desktop_colors") or []
        if desktop is None or not colors:
            return colors[-1] if colors else None
        return colors[(desktop.number - 1) % len(colors)]

    def query(self, text: str) -> List[Item]:
        show_others = bool(self.config.get("show_other_desktops", True))
        bring_here = desktops.pyvda_available()
        current, others = [], []
        for order, w in enumerate(self._windows):
            if self._excluded(w):
                continue
            if not w.on_current_desktop and not show_others:
                continue
            s = score(text, w.title, os.path.splitext(w.process_name)[0])
            if s is None:
                continue
            desktop = self._desktops.get(w.desktop_id)
            item = Item(
                title=w.title,
                subtitle=w.process_name + ("  ·  minimized" if w.minimized else ""),
                icon_path=w.exe_path,
                glyph=self.glyph,
                copy_text=w.title,
                data=w,
            )
            actions = [Action("Switch", lambda w=w: winapi.activate_window(w)), None]
            if w.on_current_desktop:
                current.append((s, order, item))
            else:
                item.badge = desktop.name if desktop else "Other desktop"
                item.color = self._color_for(desktop)
                if bring_here:
                    actions[1] = Action("Bring here", lambda w=w: self._bring_here(w))
                others.append((s, desktop.number if desktop else 999, order, item))
            actions.append(Action("Close window", lambda h=w.hwnd: winapi.close_window(h)))
            item.actions = actions

        if text.strip():
            current.sort(key=lambda t: (-t[0], t[1]))
            others.sort(key=lambda t: (t[1], -t[0], t[2]))
        else:
            others.sort(key=lambda t: (t[1], t[2]))
        items = [t[-1] for t in current] + [t[-1] for t in others]
        return items[: self.max_results]

    @staticmethod
    def _bring_here(w: winapi.WindowInfo) -> None:
        if desktops.move_window_to_current(w.hwnd):
            w.on_current_desktop = True
        winapi.force_foreground(w.hwnd)

    def initial_index(self, text: str, items: List[Item]) -> int:
        # Like Alt+Tab: Enter on an empty query returns to the previous window.
        if (
            not text.strip()
            and self.config.get("preselect_previous", True)
            and len(items) > 1
            and items[0].data is not None
            and items[0].data.hwnd == self._foreground
            and items[1].data is not None
            and items[1].data.on_current_desktop
        ):
            return 1
        return 0
