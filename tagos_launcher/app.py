"""Wires everything together: tray icon, hotkey, commands and windows."""

from __future__ import annotations

import logging
import os
from typing import Optional

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import __app_name__
from .commands import CommandRegistry
from .commands.obsidian_bookmarks import ObsidianBookmarksCommand
from .commands.web import WebCommand
from .commands.windows import WindowsCommand
from .config import load_config, save_config
from .hotkey import GlobalHotkey
from .obsidian import BookmarkIndex, guess_bookmarks_folder
from .ui import theme
from .ui.launcher_window import LauncherWindow
from .ui.settings_dialog import SettingsDialog

log = logging.getLogger(__name__)


def open_url(url: str) -> None:
    qurl = QUrl(url)
    if not qurl.scheme():
        qurl = QUrl.fromUserInput(url)
    if not QDesktopServices.openUrl(qurl):
        log.warning("Could not open %s", url)


class LauncherApp(QObject):
    def __init__(self, qapp: QApplication, server: Optional[QLocalServer] = None) -> None:
        super().__init__()
        self.qapp = qapp
        self.config = load_config()
        self._first_run_detect()
        theme.set_theme(self.config.get("theme", "dark"))

        self.index = BookmarkIndex()
        self.registry = self._build_registry()
        self.window = LauncherWindow(self.registry, self.config)
        self.window.setWindowIcon(theme.app_icon())
        self.settings_dialog: Optional[SettingsDialog] = None

        self.hotkey = GlobalHotkey(self.window.toggle)
        self.tray: Optional[QSystemTrayIcon] = None
        self._setup_tray()
        self._register_hotkey()

        if server is not None:
            server.newConnection.connect(lambda: self._on_instance_message(server))

        if self.config.get("notify_on_start") and self.tray is not None:
            self.tray.showMessage(__app_name__, f"Running — press {self.config['hotkey']} to open.",
                                  theme.app_icon(), 3000)

    # ------------------------------------------------------------ building
    def _first_run_detect(self) -> None:
        """If no bookmarks folder is set yet, look for one in your vaults."""
        obs = self.config["obsidian"]
        if not obs.get("folder"):
            guess = guess_bookmarks_folder()
            if guess:
                obs["folder"] = guess
                save_config(self.config)
                log.info("Detected Obsidian bookmarks folder: %s", guess)

    def _build_registry(self) -> CommandRegistry:
        cfg = self.config
        max_results = int(cfg.get("max_results", 50))
        obs = cfg["obsidian"]
        self.index.folder = obs.get("folder", "")
        self.index.title_field = obs.get("title_field", "title")
        self.index.aliases_field = obs.get("aliases_field", "aliases")
        self.index.url_field = obs.get("url_field", "source")
        self.index.recursive = bool(obs.get("recursive", True))
        self.index.clear()

        prefixed = []
        if obs.get("enabled", True):
            prefixed.append(ObsidianBookmarksCommand(obs, self.index, open_url, max_results))
        for entry in cfg.get("web_commands", []):
            if entry.get("prefix") and entry.get("url"):
                prefixed.append(WebCommand(entry["prefix"], entry.get("name", ""), entry["url"], open_url))
        return CommandRegistry(WindowsCommand(cfg["windows"], max_results), prefixed)

    def _register_hotkey(self) -> None:
        if not self.hotkey.register(self.config["hotkey"]) and self.tray is not None:
            if os.name == "nt":
                self.tray.showMessage(
                    __app_name__,
                    f"Couldn't register {self.config['hotkey']} — another program may be using it. "
                    "Pick a different one in Settings.",
                    QSystemTrayIcon.Warning, 6000)
        if self.tray is not None:
            self.tray.setToolTip(f"{__app_name__} — {self.config['hotkey']}")

    # ---------------------------------------------------------------- tray
    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.warning("No system tray available")
            return
        self.tray = QSystemTrayIcon(theme.app_icon(), self)
        menu = QMenu()
        menu.addAction("Open launcher").triggered.connect(lambda: self.window.open())
        menu.addAction("Search bookmarks").triggered.connect(
            lambda: self.window.open(self.config["obsidian"].get("prefix", "obs:")))
        menu.addAction("Settings…").triggered.connect(self.show_settings)
        menu.addAction("Reload bookmarks").triggered.connect(self._reload_bookmarks)
        menu.addSeparator()
        menu.addAction("Quit").triggered.connect(self.quit)
        self._tray_menu = menu  # keep a reference; the tray doesn't own it
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.window.open()

    def _reload_bookmarks(self) -> None:
        self.index.clear()
        self.index.refresh()
        if self.tray is not None:
            self.tray.showMessage(__app_name__, f"{len(self.index.bookmarks)} bookmarks loaded",
                                  theme.app_icon(), 2000)

    # ------------------------------------------------------------ settings
    def show_settings(self) -> None:
        if self.settings_dialog is not None:
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return
        self.window.hide()
        dialog = SettingsDialog(self.config)
        dialog.setWindowIcon(theme.app_icon())
        self.settings_dialog = dialog
        try:
            if dialog.exec():
                self.apply_config(dialog.result_config())
        finally:
            self.settings_dialog = None

    def apply_config(self, cfg: dict) -> None:
        self.config.clear()
        self.config.update(cfg)
        save_config(self.config)
        theme.set_theme(self.config.get("theme", "dark"))
        self.window.apply_theme()
        self.registry = self._build_registry()
        self.window.registry = self.registry
        self._register_hotkey()

    # ------------------------------------------------- single instance / IPC
    def _on_instance_message(self, server: QLocalServer) -> None:
        sock = server.nextPendingConnection()
        if sock is None:
            return

        def handle() -> None:
            command = bytes(sock.readAll()).decode("utf-8", "replace").strip()
            sock.disconnectFromServer()
            self.handle_command(command)

        if sock.bytesAvailable():
            handle()
        else:
            sock.readyRead.connect(handle)

    def handle_command(self, command: str) -> None:
        if command == "settings":
            self.show_settings()
        elif command == "quit":
            self.quit()
        elif command.startswith("show"):
            self.window.open(command[5:] if command.startswith("show:") else "")

    def quit(self) -> None:
        self.hotkey.unregister()
        if self.tray is not None:
            self.tray.hide()
        self.qapp.quit()
