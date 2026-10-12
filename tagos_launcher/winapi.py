"""Enumerate and control top-level windows (Win32 via ctypes).

:func:`list_windows` mirrors the Alt+Tab rules: visible, titled, un-owned,
non-tool windows, in Z-order (most recently used first) — plus the windows on
other virtual desktops, which Windows "cloaks" rather than hides. Every
function is a harmless no-op off Windows.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from . import desktops

log = logging.getLogger(__name__)

IS_WINDOWS = os.name == "nt"

GW_OWNER = 4
GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
WS_EX_NOACTIVATE = 0x08000000
WS_DISABLED = 0x08000000
DWMWA_CLOAKED = 14
DWM_CLOAKED_SHELL = 0x2
SW_RESTORE = 9
WM_CLOSE = 0x0010
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x2
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Shell surfaces that are technically top-level windows but never wanted.
_SKIP_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    pid: int = 0
    exe_path: str = ""
    process_name: str = ""
    class_name: str = ""
    minimized: bool = False
    desktop_id: Optional[str] = None
    on_current_desktop: bool = True


if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _dwmapi = ctypes.WinDLL("dwmapi")

    _WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = [_WNDENUMPROC, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsWindow.restype = wintypes.BOOL
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextLengthW.restype = ctypes.c_int
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetClassNameW.restype = ctypes.c_int
    _user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    _user32.GetWindow.restype = wintypes.HWND
    _GetWindowLong = getattr(_user32, "GetWindowLongPtrW", None) or _user32.GetWindowLongW
    _GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
    _GetWindowLong.restype = ctypes.c_ssize_t
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.SetForegroundWindow.restype = wintypes.BOOL
    _user32.BringWindowToTop.argtypes = [wintypes.HWND]
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.ShowWindow.restype = wintypes.BOOL
    _user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
    ]
    _kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _dwmapi.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
    ]
    _dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

    def _text(hwnd: int) -> str:
        length = _user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    def _class_name(hwnd: int) -> str:
        buf = ctypes.create_unicode_buffer(256)
        _user32.GetClassNameW(hwnd, buf, 256)
        return buf.value

    def _cloaked(hwnd: int) -> int:
        value = ctypes.c_int(0)
        if _dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(value), ctypes.sizeof(value)) != 0:
            return 0
        return value.value

    def _pid(hwnd: int) -> int:
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def _exe_path(pid: int) -> str:
        handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(1024)
            buf = ctypes.create_unicode_buffer(size.value)
            if _kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                return buf.value
            return ""
        finally:
            _kernel32.CloseHandle(handle)


def list_windows() -> List[WindowInfo]:
    """Switchable top-level windows in Z-order (empty off Windows)."""
    if not IS_WINDOWS:
        return []
    handles: List[int] = []

    def _collect(hwnd, _lparam):
        handles.append(hwnd)
        return True

    try:
        _user32.EnumWindows(_WNDENUMPROC(_collect), 0)
    except Exception:
        log.exception("EnumWindows failed")
        return []

    own_pid = os.getpid()
    exe_cache: Dict[int, str] = {}
    result: List[WindowInfo] = []
    for hwnd in handles:
        try:
            if not hwnd or not _user32.IsWindowVisible(hwnd):
                continue
            title = _text(hwnd)
            if not title:
                continue
            if _user32.GetWindow(hwnd, GW_OWNER):
                continue
            ex_style = _GetWindowLong(hwnd, GWL_EXSTYLE)
            if ex_style & WS_EX_TOOLWINDOW and not ex_style & WS_EX_APPWINDOW:
                continue
            if ex_style & WS_EX_NOACTIVATE:
                continue
            class_name = _class_name(hwnd)
            if class_name in _SKIP_CLASSES:
                continue
            desktop_id, on_current = desktops.window_desktop(hwnd)
            cloaked = _cloaked(hwnd)
            if cloaked:
                # Windows on other desktops are shell-cloaked; anything cloaked
                # for another reason (suspended UWP frames, etc.) is invisible.
                if not (cloaked & DWM_CLOAKED_SHELL) or on_current or not desktop_id:
                    continue
            pid = _pid(hwnd)
            if pid == own_pid:
                continue
            if pid not in exe_cache:
                exe_cache[pid] = _exe_path(pid)
            exe = exe_cache[pid]
            result.append(
                WindowInfo(
                    hwnd=int(hwnd),
                    title=title,
                    pid=pid,
                    exe_path=exe,
                    process_name=os.path.basename(exe) if exe else "",
                    class_name=class_name,
                    minimized=bool(_user32.IsIconic(hwnd)),
                    desktop_id=desktop_id,
                    on_current_desktop=True if on_current is None else on_current,
                )
            )
        except Exception:
            log.debug("Skipping window %s", hwnd, exc_info=True)
    return result


def foreground_window() -> int:
    if not IS_WINDOWS:
        return 0
    return int(_user32.GetForegroundWindow() or 0)


def force_foreground(hwnd: int) -> bool:
    """Bring *hwnd* to the front and give it keyboard focus.

    Windows only lets the foreground process hand focus to another window. We
    are normally foreground (the launcher has focus), but if the plain call is
    refused, a synthetic Alt tap unlocks it — a long-standing, widely used trick.
    """
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        if _user32.IsIconic(hwnd):
            _user32.ShowWindow(hwnd, SW_RESTORE)
        if _user32.SetForegroundWindow(hwnd):
            return True
        _user32.keybd_event(VK_MENU, 0, 0, 0)
        _user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        _user32.BringWindowToTop(hwnd)
        return bool(_user32.SetForegroundWindow(hwnd))
    except Exception:
        log.exception("Activating window %s failed", hwnd)
        return False


def activate_window(info: WindowInfo) -> bool:
    """Switch to a window, changing virtual desktop first if needed."""
    if not IS_WINDOWS:
        return False
    if not _user32.IsWindow(info.hwnd):
        return False
    if not info.on_current_desktop:
        # pyvda switches desktops cleanly; without it, activating the window
        # makes Windows follow it to its desktop on its own.
        desktops.switch_to_window(info.hwnd)
    return force_foreground(info.hwnd)


def close_window(hwnd: int) -> None:
    """Politely ask a window to close (same as clicking its X)."""
    if IS_WINDOWS and hwnd:
        _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
