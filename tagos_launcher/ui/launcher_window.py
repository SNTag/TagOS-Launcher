"""The pop-up launcher: a text box over a list of results."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from PySide6.QtCore import QAbstractListModel, QEvent, QFileInfo, QModelIndex, QRect, QSize, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QIcon, QPainter
from PySide6.QtWidgets import (
    QFileIconProvider,
    QFrame,
    QLabel,
    QLineEdit,
    QListView,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from .. import winapi
from ..commands import CommandRegistry, Item
from . import theme

log = logging.getLogger(__name__)

ROW_HEIGHT = 46
MAX_VISIBLE_ROWS = 9
WIDTH = 720
KEY_LABELS = ["↵", "Shift+↵", "Ctrl+↵"]


class ResultModel(QAbstractListModel):
    def __init__(self) -> None:
        super().__init__()
        self.items: List[Item] = []

    def set_items(self, items: List[Item]) -> None:
        self.beginResetModel()
        self.items = items
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.items)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        item = self.items[index.row()]
        if role == Qt.DisplayRole:
            return item.title
        if role == Qt.UserRole:
            return item
        return None


class IconCache:
    def __init__(self) -> None:
        self._provider = QFileIconProvider()
        self._cache: Dict[str, QIcon] = {}

    def for_path(self, path: str) -> Optional[QIcon]:
        if not path:
            return None
        if path not in self._cache:
            self._cache[path] = self._provider.icon(QFileInfo(path))
        icon = self._cache[path]
        return None if icon.isNull() else icon


class ResultDelegate(QStyledItemDelegate):
    def __init__(self, icons: IconCache, parent=None) -> None:
        super().__init__(parent)
        self.icons = icons

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(WIDTH, ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        item: Item = index.data(Qt.UserRole)
        p = theme.palette()
        rect = option.rect
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        if item.color:
            tint = QColor(item.color)
            tint.setAlpha(70)
            painter.fillRect(rect, tint)
            painter.fillRect(QRect(rect.left(), rect.top(), 4, rect.height()), QColor(item.color))
        if option.state & QStyle.State_Selected:
            sel = QColor(p["selection"])
            if item.color:
                sel.setAlpha(200)
            painter.fillRect(rect.adjusted(4 if item.color else 0, 0, 0, 0), sel)

        # Icon (file icon if we have one, otherwise the glyph).
        icon_rect = QRect(rect.left() + 14, rect.top() + (rect.height() - 24) // 2, 24, 24)
        icon = self.icons.for_path(item.icon_path)
        if icon is not None:
            icon.paint(painter, icon_rect)
        elif item.glyph:
            f = QFont(option.font)
            f.setPixelSize(17)
            painter.setFont(f)
            painter.setPen(QColor(p["text"]))
            painter.drawText(icon_rect, Qt.AlignCenter, item.glyph)

        left = icon_rect.right() + 12
        right = rect.right() - 12

        # Badge on the right.
        if item.badge:
            f = QFont(option.font)
            f.setPointSizeF(max(7.5, option.font.pointSizeF() * 0.85))
            painter.setFont(f)
            fm = painter.fontMetrics()
            text = fm.elidedText(item.badge, Qt.ElideRight, 180)
            w = fm.horizontalAdvance(text) + 14
            badge = QRect(right - w, rect.top() + (rect.height() - 20) // 2, w, 20)
            bg = QColor(item.color or p["button_bg"])
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(badge, 9, 9)
            painter.setPen(QColor("#ffffff") if item.color else QColor(p["text"]))
            painter.drawText(badge, Qt.AlignCenter, text)
            right = badge.left() - 10

        title_font = QFont(option.font)
        title_font.setPointSizeF(option.font.pointSizeF() * 1.08)
        painter.setFont(title_font)
        painter.setPen(QColor(p["text"]))
        fm = painter.fontMetrics()
        title_rect = QRect(left, rect.top() + 5, right - left, fm.height())
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter,
                         fm.elidedText(item.title, Qt.ElideRight, title_rect.width()))

        if item.subtitle:
            sub_font = QFont(option.font)
            sub_font.setPointSizeF(option.font.pointSizeF() * 0.88)
            painter.setFont(sub_font)
            painter.setPen(QColor(p["muted_text"]))
            fm2 = painter.fontMetrics()
            sub_rect = QRect(left, title_rect.bottom() + 2, right - left, fm2.height())
            painter.drawText(sub_rect, Qt.AlignLeft | Qt.AlignVCenter,
                             fm2.elidedText(item.subtitle, Qt.ElideRight, sub_rect.width()))
        painter.restore()


class LauncherWindow(QWidget):
    def __init__(self, registry: CommandRegistry, config: dict) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.registry = registry
        self.config = config
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("TagOS Launcher")

        self.frame = QFrame(self)
        self.frame.setObjectName("panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.frame)

        layout = QVBoxLayout(self.frame)
        layout.setContentsMargins(10, 10, 10, 8)
        layout.setSpacing(6)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Type to switch windows — or a command like obs:   (? for help)")
        self.input.textChanged.connect(self.refresh)
        self.input.installEventFilter(self)
        layout.addWidget(self.input)

        self.model = ResultModel()
        self.icons = IconCache()
        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(ResultDelegate(self.icons, self.view))
        self.view.setUniformItemSizes(True)
        self.view.setFocusPolicy(Qt.NoFocus)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.clicked.connect(lambda idx: self.run_action(0, idx.row()))
        layout.addWidget(self.view)

        self.hint = QLabel()
        layout.addWidget(self.hint)

        self.setFixedWidth(WIDTH)
        self.apply_theme()

    # ----------------------------------------------------------- appearance
    def apply_theme(self) -> None:
        p = theme.palette()
        self.frame.setStyleSheet(f"""
            QFrame#panel {{ background: {p['panel_bg']}; border: 1px solid {p['panel_border']};
                           border-radius: 10px; }}
            QLineEdit {{ background: {p['input_bg']}; color: {p['text']};
                        border: 1px solid {p['input_border']}; border-radius: 6px;
                        padding: 8px 10px; font-size: 16px; }}
            QListView {{ background: transparent; border: none; outline: none; }}
            QLabel {{ color: {p['muted_text']}; background: transparent; padding: 0 4px; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; }}
            QScrollBar::handle:vertical {{ background: {p['input_border']}; border-radius: 4px; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
        """)

    # ------------------------------------------------------------- showing
    def open(self, text: str = "") -> None:
        try:
            self.registry.on_open()  # snapshot windows before we take focus
        except Exception:
            log.exception("Refreshing commands failed")
        self.input.blockSignals(True)
        self.input.setText(text)
        self.input.blockSignals(False)
        self.refresh()
        self._position()
        self.show()
        self.raise_()
        self.activateWindow()
        winapi.force_foreground(int(self.winId()))
        self.input.setFocus()

    def _position(self) -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        self.move(geo.left() + (geo.width() - self.width()) // 2, geo.top() + int(geo.height() * 0.2))

    def toggle(self) -> None:
        if self.isVisible() and self.isActiveWindow():
            self.hide()
        else:
            self.open()

    def event(self, ev) -> bool:
        if ev.type() == QEvent.WindowDeactivate and self.config.get("hide_on_focus_loss", True):
            self.hide()
        return super().event(ev)

    # ------------------------------------------------------------- results
    def refresh(self) -> None:
        text = self.input.text()
        cmd, rest = self.registry.resolve(text)
        try:
            items = cmd.query(rest)
        except Exception:
            log.exception("Command %s failed", cmd.name)
            items = [Item(title=f"{cmd.name} failed", subtitle="See launcher.log for details", glyph="⚠")]
        if cmd is self.registry.default:
            items = items + self.registry.suggestions(text)
        self.model.set_items(items)
        if items:
            self._select(cmd.initial_index(rest, items))
        rows = max(1, min(len(items), MAX_VISIBLE_ROWS))
        self.view.setFixedHeight(rows * ROW_HEIGHT + 2)
        self._update_hint()
        self.adjustSize()

    def _select(self, row: int) -> None:
        if not self.model.items:
            return
        row = max(0, min(row, len(self.model.items) - 1))
        idx = self.model.index(row)
        self.view.setCurrentIndex(idx)
        self.view.scrollTo(idx)
        self._update_hint()

    def _current_row(self) -> int:
        idx = self.view.currentIndex()
        return idx.row() if idx.isValid() else 0

    def _update_hint(self) -> None:
        if not self.model.items:
            self.hint.setText("No results")
            return
        item = self.model.items[self._current_row()]
        parts = [f"{KEY_LABELS[i]} {a.label}" for i, a in enumerate(item.actions[:3]) if a]
        if item.copy_text:
            parts.append("Ctrl+C copy")
        parts.append("Esc close")
        self.hint.setText("    ".join(parts))

    # -------------------------------------------------------------- input
    def eventFilter(self, obj, ev) -> bool:  # noqa: N802
        if obj is self.input and ev.type() == QEvent.KeyPress:
            key, mods = ev.key(), ev.modifiers()
            count = len(self.model.items)
            if key == Qt.Key_Escape:
                if self.input.text():
                    self.input.clear()
                else:
                    self.hide()
                return True
            if key in (Qt.Key_Down, Qt.Key_Up) and count:
                step = 1 if key == Qt.Key_Down else -1
                self._select((self._current_row() + step) % count)
                return True
            if key in (Qt.Key_PageDown, Qt.Key_PageUp) and count:
                step = MAX_VISIBLE_ROWS if key == Qt.Key_PageDown else -MAX_VISIBLE_ROWS
                self._select(self._current_row() + step)
                return True
            if key == Qt.Key_Tab:
                item = self.model.items[self._current_row()] if count else None
                fill = next((a.fill for a in (item.actions if item else []) if a and a.fill), None)
                if fill is not None:
                    self.input.setText(fill)
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if mods & Qt.ControlModifier:
                    self.run_action(2)
                elif mods & Qt.ShiftModifier:
                    self.run_action(1)
                else:
                    self.run_action(0)
                return True
            if key == Qt.Key_C and mods & Qt.ControlModifier and not self.input.hasSelectedText() and count:
                item = self.model.items[self._current_row()]
                if item.copy_text:
                    QGuiApplication.clipboard().setText(item.copy_text)
                    self.hide()
                    return True
        return super().eventFilter(obj, ev)

    def run_action(self, which: int, row: Optional[int] = None) -> None:
        if not self.model.items:
            return
        item = self.model.items[self._current_row() if row is None else row]
        if which >= len(item.actions):
            return
        action = item.actions[which]
        if action is None:
            return
        if action.fill is not None:
            self.input.setText(action.fill)
            self.input.setFocus()
            return
        # Run while we still own the foreground, so focus can be handed over;
        # then get out of the way.
        try:
            if action.callback:
                action.callback()
        except Exception:
            log.exception("Action %r failed", action.label)
        self.hide()
