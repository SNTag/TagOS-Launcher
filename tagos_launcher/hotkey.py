"""System-wide hotkey via the Win32 ``RegisterHotKey`` API.

Hotkeys are stored as Qt "portable text" (e.g. ``Ctrl+Alt+Space``,
``Meta+K``), which is what the settings dialog's key recorder produces.
:func:`parse_hotkey` turns that into Win32 modifier flags + a virtual-key code.
On non-Windows platforms registration is a harmless no-op that reports failure.
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional, Tuple

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QTimer

log = logging.getLogger(__name__)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312

_MODIFIERS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "meta": MOD_WIN,
    "win": MOD_WIN,
    "super": MOD_WIN,
}

_NAMED_KEYS = {
    "space": 0x20,
    "tab": 0x09,
    "return": 0x0D,
    "enter": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "ins": 0x2D,
    "insert": 0x2D,
    "del": 0x2E,
    "delete": 0x2E,
    "home": 0x24,
    "end": 0x23,
    "pgup": 0x21,
    "pageup": 0x21,
    "pgdown": 0x22,
    "pagedown": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "pause": 0x13,
    "print": 0x2C,
    "capslock": 0x14,
    ";": 0xBA,
    "=": 0xBB,
    ",": 0xBC,
    "-": 0xBD,
    ".": 0xBE,
    "/": 0xBF,
    "`": 0xC0,
    "[": 0xDB,
    "\\": 0xDC,
    "]": 0xDD,
    "'": 0xDE,
}


def _vk_for(key: str) -> Optional[int]:
    if len(key) == 1 and key.isalnum():
        return ord(key.upper())
    lowered = key.lower()
    if lowered in _NAMED_KEYS:
        return _NAMED_KEYS[lowered]
    if lowered.startswith("f") and lowered[1:].isdigit():
        n = int(lowered[1:])
        if 1 <= n <= 24:
            return 0x6F + n
    return None


def parse_hotkey(text: str) -> Optional[Tuple[int, int]]:
    """``"Ctrl+Alt+Space"`` -> ``(MOD_CONTROL | MOD_ALT, VK_SPACE)``.

    Returns None if the text has no recognisable key or no modifier (a bare
    key as a global hotkey would swallow normal typing).
    """
    if not text:
        return None
    parts = [p.strip() for p in text.split("+")]
    if text.endswith("++"):  # the "+" key itself
        parts = parts[:-2] + ["="]  # VK_OEM_PLUS shares the =/+ key
    mods = 0
    vk: Optional[int] = None
    for part in parts:
        if not part:
            continue
        mod = _MODIFIERS.get(part.lower())
        if mod is not None:
            mods |= mod
        else:
            vk = _vk_for(part)
            if vk is None:
                return None
    if vk is None or mods == 0:
        return None
    return mods, vk


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, hotkey_id: int, callback: Callable[[], None]) -> None:
        super().__init__()
        self._id = hotkey_id
        self._callback = callback

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt API)
        try:
            name = event_type.data() if hasattr(event_type, "data") else bytes(event_type)
            if name.startswith(b"windows"):
                from ctypes import wintypes

                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and msg.wParam == self._id:
                    # Don't do real work inside the native filter.
                    QTimer.singleShot(0, self._callback)
                    return True, 0
        except Exception:  # never let an exception escape into Qt's loop
            log.exception("hotkey filter failed")
        return False, 0


class GlobalHotkey:
    """One registered global hotkey that calls *callback* when pressed."""

    HOTKEY_ID = 0x7A61  # arbitrary, unique within this process

    def __init__(self, callback: Callable[[], None]) -> None:
        self._filter = _HotkeyFilter(self.HOTKEY_ID, callback)
        self._registered = False
        self._installed = False

    def register(self, text: str) -> bool:
        """(Re)register the hotkey; returns False if Windows refused it
        (usually because another program already owns that combination)."""
        self.unregister()
        if os.name != "nt":
            log.info("Global hotkeys are only supported on Windows")
            return False
        parsed = parse_hotkey(text)
        if parsed is None:
            log.warning("Unrecognised hotkey %r", text)
            return False
        mods, vk = parsed
        import ctypes

        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, self.HOTKEY_ID, mods | MOD_NOREPEAT, vk):
            log.warning("RegisterHotKey failed for %r (already in use?)", text)
            return False
        if not self._installed:
            QCoreApplication.instance().installNativeEventFilter(self._filter)
            self._installed = True
        self._registered = True
        log.info("Registered hotkey %s", text)
        return True

    def unregister(self) -> None:
        if self._registered and os.name == "nt":
            import ctypes

            ctypes.windll.user32.UnregisterHotKey(None, self.HOTKEY_ID)
        self._registered = False
