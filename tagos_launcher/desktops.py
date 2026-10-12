"""Windows virtual desktops: which desktops exist and which one a window is on.

Two layers, so the launcher keeps working across Windows builds:

* **Documented APIs (always used).** The ``IVirtualDesktopManager`` COM
  interface tells us each window's desktop GUID and whether it's on the current
  desktop; the registry holds the desktop order and any names you gave them.
* **pyvda (optional).** If installed, it's used to jump straight to a window on
  another desktop and to pull a window onto the current desktop — things the
  documented API can't do for other processes' windows. If it's missing or
  doesn't support your Windows build, those extras quietly fall back.

Everything here is a no-op off Windows and never raises.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

log = logging.getLogger(__name__)

IS_WINDOWS = os.name == "nt"

_VD_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VirtualDesktops"
_CLSID_VIRTUAL_DESKTOP_MANAGER = "{AA509086-5CA9-4C25-8F95-589D3C07B48A}"
_IID_IVIRTUAL_DESKTOP_MANAGER = "{A5CD92FF-29BE-454C-8D04-D82879FB3F1B}"


@dataclass
class Desktop:
    id: str  # lower-case GUID without braces
    number: int  # 1-based position, as shown in Task View
    name: str


@dataclass
class DesktopInfo:
    desktops: List[Desktop] = field(default_factory=list)
    current_id: Optional[str] = None

    def get(self, desktop_id: Optional[str]) -> Optional[Desktop]:
        if not desktop_id:
            return None
        for d in self.desktops:
            if d.id == desktop_id:
                return d
        return None


# ---------------------------------------------------------------- COM (ctypes)
class _VirtualDesktopManager:
    """Minimal ctypes binding of the documented IVirtualDesktopManager."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._wintypes = wintypes
        ole32 = ctypes.windll.ole32
        ole32.CoInitializeEx(None, 0x2)  # apartment-threaded; S_FALSE if already done

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        self.GUID = GUID
        clsid, iid = GUID(), GUID()
        ole32.CLSIDFromString(_CLSID_VIRTUAL_DESKTOP_MANAGER, ctypes.byref(clsid))
        ole32.CLSIDFromString(_IID_IVIRTUAL_DESKTOP_MANAGER, ctypes.byref(iid))
        self._ptr = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(clsid), None, 0x1 | 0x4, ctypes.byref(iid), ctypes.byref(self._ptr)
        )
        if hr != 0 or not self._ptr:
            raise OSError(f"CoCreateInstance(VirtualDesktopManager) failed: {hr:#x}")
        vtbl = ctypes.cast(self._ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        proto = ctypes.WINFUNCTYPE
        # vtable: QueryInterface, AddRef, Release, IsWindowOnCurrentVirtualDesktop,
        #         GetWindowDesktopId, MoveWindowToDesktop
        self._is_on_current = proto(
            ctypes.c_long, ctypes.c_void_p, wintypes.HWND, ctypes.POINTER(wintypes.BOOL)
        )(vtbl[3])
        self._get_desktop_id = proto(
            ctypes.c_long, ctypes.c_void_p, wintypes.HWND, ctypes.POINTER(GUID)
        )(vtbl[4])

    def window_desktop(self, hwnd: int) -> Tuple[Optional[str], Optional[bool]]:
        ctypes, wintypes = self._ctypes, self._wintypes
        on_current: Optional[bool] = None
        flag = wintypes.BOOL()
        if self._is_on_current(self._ptr, hwnd, ctypes.byref(flag)) == 0:
            on_current = bool(flag.value)
        desktop_id: Optional[str] = None
        guid = self.GUID()
        if self._get_desktop_id(self._ptr, hwnd, ctypes.byref(guid)) == 0:
            parsed = uuid.UUID(bytes_le=bytes(guid))
            if parsed.int:
                desktop_id = str(parsed)
        return desktop_id, on_current


_manager: Optional[_VirtualDesktopManager] = None
_manager_failed = False


def _get_manager() -> Optional[_VirtualDesktopManager]:
    global _manager, _manager_failed
    if _manager is None and not _manager_failed and IS_WINDOWS:
        try:
            _manager = _VirtualDesktopManager()
        except Exception:
            log.exception("Virtual desktop API unavailable")
            _manager_failed = True
    return _manager


def window_desktop(hwnd: int) -> Tuple[Optional[str], Optional[bool]]:
    """``(desktop_id, on_current_desktop)`` for *hwnd*; unknowns are None."""
    manager = _get_manager()
    if manager is None:
        return None, None
    try:
        return manager.window_desktop(hwnd)
    except Exception:
        return None, None


# -------------------------------------------------------------------- registry
def _registry_desktops() -> DesktopInfo:
    import winreg

    info = DesktopInfo()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _VD_KEY) as key:
            raw, _ = winreg.QueryValueEx(key, "VirtualDesktopIDs")
            try:
                cur, _ = winreg.QueryValueEx(key, "CurrentVirtualDesktop")
                info.current_id = str(uuid.UUID(bytes_le=bytes(cur)))
            except OSError:
                pass
    except OSError:
        return info
    raw = bytes(raw or b"")
    for i in range(0, len(raw) - len(raw) % 16, 16):
        desktop_id = str(uuid.UUID(bytes_le=raw[i : i + 16]))
        number = i // 16 + 1
        name = ""
        try:
            sub = _VD_KEY + r"\Desktops\{" + desktop_id.upper() + "}"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub) as key:
                name, _ = winreg.QueryValueEx(key, "Name")
        except OSError:
            pass
        info.desktops.append(Desktop(desktop_id, number, name or f"Desktop {number}"))
    if info.current_id is None:
        # Windows 10 keeps the current desktop under the per-session key.
        try:
            import ctypes

            session = ctypes.c_ulong()
            ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session))
            sub = (
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\SessionInfo"
                + "\\" + str(session.value) + r"\VirtualDesktops"
            )
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub) as key:
                cur, _ = winreg.QueryValueEx(key, "CurrentVirtualDesktop")
                info.current_id = str(uuid.UUID(bytes_le=bytes(cur)))
        except Exception:
            pass
    return info


# ----------------------------------------------------------------------- pyvda
def _pyvda():
    try:
        import pyvda  # type: ignore

        return pyvda
    except Exception:
        return None


def pyvda_available() -> bool:
    return IS_WINDOWS and _pyvda() is not None


def _pyvda_desktops() -> Optional[DesktopInfo]:
    pyvda = _pyvda()
    if pyvda is None:
        return None
    try:
        info = DesktopInfo()
        for vd in pyvda.get_virtual_desktops():
            name = ""
            try:
                name = vd.name or ""
            except Exception:
                pass
            desktop_id = str(uuid.UUID(str(vd.id)))
            info.desktops.append(Desktop(desktop_id, vd.number, name or f"Desktop {vd.number}"))
        info.current_id = str(uuid.UUID(str(pyvda.VirtualDesktop.current().id)))
        return info
    except Exception:
        log.debug("pyvda desktop listing failed", exc_info=True)
        return None


def snapshot() -> DesktopInfo:
    """Current list of desktops (in Task View order) and the active one."""
    if not IS_WINDOWS:
        return DesktopInfo()
    info = _pyvda_desktops()
    if info is not None and info.desktops:
        return info
    try:
        return _registry_desktops()
    except Exception:
        log.exception("Reading virtual desktops from the registry failed")
        return DesktopInfo()


def switch_to_window(hwnd: int) -> bool:
    """Switch to *hwnd*'s desktop and focus it (pyvda). False if unavailable."""
    pyvda = _pyvda()
    if pyvda is None:
        return False
    try:
        pyvda.AppView(hwnd=hwnd).switch_to()
        return True
    except Exception:
        log.debug("pyvda switch_to failed", exc_info=True)
        return False


def move_window_to_current(hwnd: int) -> bool:
    """Move *hwnd* onto the current desktop (pyvda). False if unavailable."""
    pyvda = _pyvda()
    if pyvda is None:
        return False
    try:
        pyvda.AppView(hwnd=hwnd).move(pyvda.VirtualDesktop.current())
        return True
    except Exception:
        log.debug("pyvda move failed", exc_info=True)
        return False

