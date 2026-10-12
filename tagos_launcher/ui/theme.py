"""Light/dark palettes (matching TagOS Manager) and the app icon."""

from __future__ import annotations

from typing import Dict

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

PALETTES: Dict[str, Dict[str, str]] = {
    "dark": {
        "window_bg": "#1e1e28",
        "panel_bg": "#1e1e28",
        "panel_border": "#4a4a6a",
        "text": "#e6e6f0",
        "muted_text": "#8a8a99",
        "input_bg": "#15151d",
        "input_border": "#34344a",
        "selection": "#3d3d5c",
        "accent": "#2e7d4f",
        "button_bg": "#34344a",
        "button_hover": "#42425e",
    },
    "light": {
        "window_bg": "#f4f4f7",
        "panel_bg": "#ffffff",
        "panel_border": "#b0b0c4",
        "text": "#1e1e28",
        "muted_text": "#6a6a78",
        "input_bg": "#f4f4f7",
        "input_border": "#cfcfda",
        "selection": "#dcdcec",
        "accent": "#2e7d4f",
        "button_bg": "#e4e4ec",
        "button_hover": "#d4d4e0",
    },
}

_current = "dark"


def set_theme(name: str) -> None:
    global _current
    _current = name if name in PALETTES else "dark"


def palette() -> Dict[str, str]:
    return PALETTES[_current]


def dialog_stylesheet() -> str:
    p = palette()
    return f"""
    QWidget {{ background: {p['window_bg']}; color: {p['text']}; }}
    QLineEdit, QPlainTextEdit, QSpinBox, QComboBox, QKeySequenceEdit, QTableWidget {{
        background: {p['input_bg']}; border: 1px solid {p['input_border']};
        border-radius: 4px; padding: 3px;
    }}
    QPushButton {{
        background: {p['button_bg']}; border: none; border-radius: 4px; padding: 5px 12px;
    }}
    QPushButton:hover {{ background: {p['button_hover']}; }}
    QTabWidget::pane {{ border: 1px solid {p['input_border']}; }}
    QTabBar::tab {{ background: {p['input_bg']}; padding: 6px 14px; }}
    QTabBar::tab:selected {{ background: {p['button_bg']}; }}
    QHeaderView::section {{ background: {p['button_bg']}; border: none; padding: 4px; }}
    """


def app_icon() -> QIcon:
    """A simple generated icon (rounded square with a "T")."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 256):
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#2e7d4f"))
        painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
        font = QFont("Segoe UI")
        font.setBold(True)
        font.setPixelSize(int(size * 0.68))
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, "T")
        painter.end()
        icon.addPixmap(pix)
    return icon
