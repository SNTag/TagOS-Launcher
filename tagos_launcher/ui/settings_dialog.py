"""Settings window: hotkey, appearance, windows, Obsidian and web commands."""

from __future__ import annotations

import copy
import os
from typing import Any, Dict, List

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import desktops
from ..config import DEFAULT_CONFIG
from ..hotkey import parse_hotkey
from ..obsidian import BookmarkIndex, GUESS_FOLDER_NAMES, find_vaults
from . import theme


def _note(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {theme.palette()['muted_text']};")
    return label


class SettingsDialog(QDialog):
    def __init__(self, config: Dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("TagOS Launcher — Settings")
        self.setStyleSheet(theme.dialog_stylesheet())
        self.resize(640, 560)
        self.config = copy.deepcopy(config)

        tabs = QTabWidget()
        tabs.addTab(self._general_tab(), "General")
        tabs.addTab(self._windows_tab(), "Windows")
        tabs.addTab(self._obsidian_tab(), "Obsidian")
        tabs.addTab(self._web_tab(), "Web commands")

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        self.error = QLabel()
        self.error.setStyleSheet("color: #e06c75;")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(self.error)
        layout.addWidget(buttons)

    # -------------------------------------------------------------- General
    def _general_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.hotkey = QKeySequenceEdit(QKeySequence(self.config["hotkey"]))
        if hasattr(self.hotkey, "setMaximumSequenceLength"):
            self.hotkey.setMaximumSequenceLength(1)
        reset = QPushButton("Default")
        reset.clicked.connect(lambda: self.hotkey.setKeySequence(QKeySequence(DEFAULT_CONFIG["hotkey"])))
        row = QHBoxLayout()
        row.addWidget(self.hotkey, 1)
        row.addWidget(reset)
        form.addRow("Launcher hotkey:", row)
        form.addRow("", _note("Click the box and press the combination. It must include Ctrl, Alt, "
                              "Shift or Win. If another program already uses it, the tray icon will say so."))

        self.theme = QComboBox()
        self.theme.addItems(["dark", "light"])
        self.theme.setCurrentText(self.config.get("theme", "dark"))
        form.addRow("Theme:", self.theme)

        self.max_results = QSpinBox()
        self.max_results.setRange(5, 500)
        self.max_results.setValue(int(self.config.get("max_results", 50)))
        form.addRow("Max results:", self.max_results)

        self.hide_on_blur = QCheckBox("Hide the launcher when it loses focus")
        self.hide_on_blur.setChecked(bool(self.config.get("hide_on_focus_loss", True)))
        form.addRow(self.hide_on_blur)
        self.notify = QCheckBox("Show a tray notification when the launcher starts")
        self.notify.setChecked(bool(self.config.get("notify_on_start", False)))
        form.addRow(self.notify)
        return w

    # -------------------------------------------------------------- Windows
    def _windows_tab(self) -> QWidget:
        cfg = self.config["windows"]
        w = QWidget()
        layout = QVBoxLayout(w)
        self.show_others = QCheckBox("List windows on other virtual desktops (below the current desktop's)")
        self.show_others.setChecked(bool(cfg.get("show_other_desktops", True)))
        layout.addWidget(self.show_others)
        self.preselect = QCheckBox("With nothing typed, preselect the previous window (Alt+Tab style)")
        self.preselect.setChecked(bool(cfg.get("preselect_previous", True)))
        layout.addWidget(self.preselect)

        layout.addWidget(QLabel("Row colour for each desktop:"))
        grid = QGridLayout()
        names = {d.number: d.name for d in desktops.snapshot().desktops}
        self.colors: List[str] = list(cfg.get("desktop_colors") or DEFAULT_CONFIG["windows"]["desktop_colors"])
        self.color_buttons: List[QPushButton] = []
        for i, color in enumerate(self.colors):
            btn = QPushButton(names.get(i + 1, f"Desktop {i + 1}"))
            btn.clicked.connect(lambda _=False, i=i: self._pick_color(i))
            self.color_buttons.append(btn)
            grid.addWidget(btn, i // 4, i % 4)
            self._paint_color_button(i)
        layout.addLayout(grid)
        if not desktops.pyvda_available():
            layout.addWidget(_note("Tip: install the optional 'pyvda' package (it's in requirements.txt) "
                                   "to jump straight to windows on other desktops and to use "
                                   "Shift+Enter → 'Bring here'."))

        layout.addWidget(QLabel("Hide these windows (process name like 'notepad.exe', or text in the title), one per line:"))
        self.exclude = QPlainTextEdit("\n".join(cfg.get("exclude", [])))
        layout.addWidget(self.exclude, 1)
        return w

    def _paint_color_button(self, i: int) -> None:
        self.color_buttons[i].setStyleSheet(
            f"background: {self.colors[i]}; color: #ffffff; padding: 6px; border-radius: 4px;"
        )

    def _pick_color(self, i: int) -> None:
        color = QColorDialog.getColor(QColor(self.colors[i]), self, "Desktop colour")
        if color.isValid():
            self.colors[i] = color.name()
            self._paint_color_button(i)

    # ------------------------------------------------------------- Obsidian
    def _obsidian_tab(self) -> QWidget:
        cfg = self.config["obsidian"]
        w = QWidget()
        form = QFormLayout(w)
        self.obs_enabled = QCheckBox("Enable the Obsidian bookmarks command")
        self.obs_enabled.setChecked(bool(cfg.get("enabled", True)))
        form.addRow(self.obs_enabled)

        self.obs_prefix = QLineEdit(cfg.get("prefix", "obs:"))
        form.addRow("Command prefix:", self.obs_prefix)

        self.obs_folder = QLineEdit(cfg.get("folder", ""))
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_folder)
        detect = QPushButton("From vault ▾")
        detect.clicked.connect(lambda: self._vault_menu(detect))
        row = QHBoxLayout()
        row.addWidget(self.obs_folder, 1)
        row.addWidget(browse)
        row.addWidget(detect)
        form.addRow("Bookmarks folder:", row)
        self.obs_recursive = QCheckBox("Include sub-folders")
        self.obs_recursive.setChecked(bool(cfg.get("recursive", True)))
        form.addRow("", self.obs_recursive)

        form.addRow(_note("Frontmatter fields to read. Several names may be given, separated by commas "
                          "(the first one present is used; aliases from all of them are combined)."))
        self.obs_title = QLineEdit(cfg.get("title_field", "title"))
        form.addRow("Title field:", self.obs_title)
        form.addRow("", _note("Falls back to the note's file name when the field is missing."))
        self.obs_aliases = QLineEdit(cfg.get("aliases_field", "aliases"))
        form.addRow("Aliases field:", self.obs_aliases)
        self.obs_url = QLineEdit(cfg.get("url_field", "source"))
        form.addRow("URL field:", self.obs_url)

        self.obs_without = QComboBox()
        self.obs_without.addItem("List them — Enter opens the note in Obsidian", "obsidian")
        self.obs_without.addItem("Hide them", "hide")
        self.obs_without.setCurrentIndex(0 if cfg.get("without_url", "obsidian") != "hide" else 1)
        form.addRow("Notes without a URL:", self.obs_without)

        test = QPushButton("Test: count bookmarks")
        self.obs_status = QLabel()
        test.clicked.connect(self._test_folder)
        row2 = QHBoxLayout()
        row2.addWidget(test)
        row2.addWidget(self.obs_status, 1)
        form.addRow(row2)
        return w

    def _browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Bookmarks folder", self.obs_folder.text())
        if path:
            self.obs_folder.setText(os.path.normpath(path))

    def _vault_menu(self, anchor: QPushButton) -> None:
        menu = QMenu(self)
        vaults = find_vaults()
        if not vaults:
            menu.addAction("No Obsidian vaults found").setEnabled(False)
        for vault in vaults:
            sub = menu.addMenu(os.path.basename(vault) or vault)
            sub.addAction("(vault root)").triggered.connect(lambda _=False, p=vault: self.obs_folder.setText(p))
            try:
                folders = sorted(
                    e.name for e in os.scandir(vault) if e.is_dir() and not e.name.startswith(".")
                )
            except OSError:
                folders = []
            folders.sort(key=lambda n: n not in GUESS_FOLDER_NAMES)
            for name in folders:
                path = os.path.join(vault, name)
                sub.addAction(name).triggered.connect(lambda _=False, p=path: self.obs_folder.setText(p))
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _test_folder(self) -> None:
        index = BookmarkIndex(self.obs_folder.text().strip(), self.obs_title.text(),
                              self.obs_aliases.text(), self.obs_url.text(), self.obs_recursive.isChecked())
        if not os.path.isdir(index.folder):
            self.obs_status.setText("Folder not found")
            return
        index.refresh()
        notes = index.bookmarks
        with_url = sum(1 for b in notes if b.url)
        aliases = sum(1 for b in notes if b.aliases)
        self.obs_status.setText(f"{len(notes)} notes · {with_url} with a URL · {aliases} with aliases")

    # --------------------------------------------------------- Web commands
    def _web_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(_note("Type the prefix followed by a search, e.g. 'g: pyside6 tray icon'. "
                               "{query} in the URL is replaced by what you type."))
        self.web = QTableWidget(0, 3)
        self.web.setHorizontalHeaderLabels(["Prefix", "Name", "URL template"])
        self.web.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.web.verticalHeader().setVisible(False)
        for entry in self.config.get("web_commands", []):
            self._add_web_row(entry.get("prefix", ""), entry.get("name", ""), entry.get("url", ""))
        layout.addWidget(self.web, 1)
        row = QHBoxLayout()
        add = QPushButton("Add")
        add.clicked.connect(lambda: self._add_web_row("", "", "https://example.com/search?q={query}"))
        remove = QPushButton("Remove selected")
        remove.clicked.connect(lambda: self.web.removeRow(self.web.currentRow()))
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        layout.addLayout(row)
        return w

    def _add_web_row(self, prefix: str, name: str, url: str) -> None:
        r = self.web.rowCount()
        self.web.insertRow(r)
        for c, value in enumerate((prefix, name, url)):
            self.web.setItem(r, c, QTableWidgetItem(value))

    # ----------------------------------------------------------------- save
    def _accept(self) -> None:
        hotkey = self.hotkey.keySequence().toString(QKeySequence.PortableText)
        if parse_hotkey(hotkey) is None:
            self.error.setText(f"“{hotkey or 'nothing'}” isn't a usable hotkey — include Ctrl, Alt, Shift or Win.")
            return
        prefixes = []
        web = []
        for r in range(self.web.rowCount()):
            cells = [(self.web.item(r, c).text().strip() if self.web.item(r, c) else "") for c in range(3)]
            if not cells[0] and not cells[2]:
                continue
            if not cells[0] or "{query}" not in cells[2]:
                self.error.setText(f"Web command row {r + 1} needs a prefix and a URL containing {{query}}.")
                return
            web.append({"prefix": cells[0], "name": cells[1] or cells[0], "url": cells[2]})
            prefixes.append(cells[0].lower())
        obs_prefix = self.obs_prefix.text().strip() or "obs:"
        if self.obs_enabled.isChecked():
            prefixes.append(obs_prefix.lower())
        if len(set(prefixes)) != len(prefixes):
            self.error.setText("Two commands share the same prefix.")
            return

        c = self.config
        c["hotkey"] = hotkey
        c["theme"] = self.theme.currentText()
        c["max_results"] = self.max_results.value()
        c["hide_on_focus_loss"] = self.hide_on_blur.isChecked()
        c["notify_on_start"] = self.notify.isChecked()
        c["windows"].update({
            "show_other_desktops": self.show_others.isChecked(),
            "preselect_previous": self.preselect.isChecked(),
            "desktop_colors": self.colors,
            "exclude": [l.strip() for l in self.exclude.toPlainText().splitlines() if l.strip()],
        })
        c["obsidian"].update({
            "enabled": self.obs_enabled.isChecked(),
            "prefix": obs_prefix,
            "folder": self.obs_folder.text().strip(),
            "recursive": self.obs_recursive.isChecked(),
            "title_field": self.obs_title.text().strip() or "title",
            "aliases_field": self.obs_aliases.text().strip(),
            "url_field": self.obs_url.text().strip() or "source",
            "without_url": self.obs_without.currentData(),
        })
        c["web_commands"] = web
        self.accept()

    def result_config(self) -> Dict[str, Any]:
        return self.config
