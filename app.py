import sys
import os
import shutil
import ctypes
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTextEdit, QListWidget, QListWidgetItem,
    QAbstractItemView, QTableWidget, QTableWidgetItem, QHeaderView,
    QCheckBox, QMessageBox, QFrame, QSplitter, QFileDialog, QGraphicsDropShadowEffect,
    QDialog, QLineEdit, QDialogButtonBox, QGraphicsOpacityEffect, QColorDialog,
    QButtonGroup
)
from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QSize, QTimer, QThread, QSettings
from PyQt5.QtGui import QDragEnterEvent, QDropEvent, QIcon, QFont, QColor, QCursor, QPainter, QKeySequence, QPixmap

import license_core
import updater

# Set Windows AppUserModelID so taskbar displays the custom app icon
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Offset.AutoRenamer.GUI.1")
except Exception:
    pass

def load_multi_res_icon() -> QIcon:
    """
    Loads multi-resolution icon for Windows taskbar, title bar, and Alt+Tab menu.
    """
    base_dir = Path(__file__).parent
    ico_file = base_dir / "icon.ico"
    png_file = base_dir / "illust.png"

    icon = QIcon()
    if ico_file.exists():
        for size in (16, 20, 24, 32, 40, 48, 64, 96, 128, 256):
            icon.addFile(str(ico_file), QSize(size, size))
    elif png_file.exists():
        icon.addFile(str(png_file))
    return icon

# --- Offset Shop: dark theme with a user-selectable accent color ---
DANGER = "#F87171"
SUCCESS = "#34D399"
WARNING = "#FBBF24"

DEFAULT_ACCENT = "#7C9CF8"  # modern indigo-blue

# Curated presets shown in the accent picker. (label, hex)
ACCENT_PRESETS = [
    ("Indigo", "#7C9CF8"),
    ("Silver", "#E5E7EB"),
    ("Emerald", "#34D399"),
    ("Amber", "#FBBF24"),
    ("Rose", "#FB7185"),
    ("Violet", "#A78BFA"),
    ("Cyan", "#22D3EE"),
    ("Orange", "#FB923C"),
]

_SETTINGS_ORG = "OffsetShop"
_SETTINGS_APP = "OffsetAutoRenamer"


def _blend(hex_a: str, hex_b: str, t: float) -> str:
    """Blend hex_a toward hex_b by fraction t (0..1)."""
    ca, cb = QColor(hex_a), QColor(hex_b)
    r = round(ca.red() * (1 - t) + cb.red() * t)
    g = round(ca.green() * (1 - t) + cb.green() * t)
    b = round(ca.blue() * (1 - t) + cb.blue() * t)
    return QColor(r, g, b).name()


def _lighten(hex_color: str, amount: float) -> str:
    return _blend(hex_color, "#FFFFFF", amount)


def _readable_text(hex_color: str) -> str:
    """Pick black or white text so it stays legible on top of any accent color."""
    c = QColor(hex_color)
    luminance = (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255
    return "#0B0C0E" if luminance > 0.62 else "#FFFFFF"


def load_saved_accent() -> str:
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    value = settings.value("accent_color", DEFAULT_ACCENT, type=str)
    return value if QColor(value).isValid() else DEFAULT_ACCENT


def save_accent(hex_color: str):
    settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.setValue("accent_color", hex_color)


class Theme:
    """
    Holds the current accent color plus every shade derived from it.
    Backgrounds are the same near-black base as before, just subtly tinted
    toward the chosen accent -- so picking a new accent visibly reshades
    the whole app, not just the buttons.
    """

    def __init__(self, accent_hex: str = DEFAULT_ACCENT):
        self.set_accent(accent_hex)

    def set_accent(self, accent_hex: str):
        accent_hex = accent_hex if QColor(accent_hex).isValid() else DEFAULT_ACCENT
        self.accent = QColor(accent_hex).name()
        self.accent_light = _lighten(self.accent, 0.24)
        self.accent_dim = _blend(self.accent, "#9CA3AF", 0.55)
        self.accent_text = _readable_text(self.accent)

        # Backgrounds: near-black bases, subtly tinted with the chosen accent
        self.bg_main = _blend("#0B0C0E", self.accent, 0.07)
        self.bg_card = _blend("#131519", self.accent, 0.06)
        self.bg_card_alt = _blend("#131519", self.accent, 0.11)
        self.bg_input = _blend("#0F1114", self.accent, 0.06)
        self.bg_list_item = _blend("#16181C", self.accent, 0.06)
        self.bg_list_item_hover = _blend("#1C1F25", self.accent, 0.10)
        self.bg_list_item_selected = _blend("#22252B", self.accent, 0.16)
        self.bg_button = _blend("#1B1E23", self.accent, 0.07)
        self.bg_button_hover = _blend("#24272E", self.accent, 0.11)
        self.bg_button_pressed = _blend("#101216", self.accent, 0.05)
        self.bg_badge = _blend("#1D2026", self.accent, 0.12)

        self.border = _blend("#26292F", self.accent, 0.18)
        self.border_soft = _blend("#2A2D33", self.accent, 0.16)
        self.border_strong = _blend("#3A3D44", self.accent, 0.22)


# Active theme instance -- created once and mutated in place via set_accent()
# so every open widget picks up the new colors after the stylesheet refresh.
theme = Theme(load_saved_accent())


def build_stylesheet(t: "Theme") -> str:
    return f"""
QMainWindow {{
    background-color: {t.bg_main};
}}

QDialog {{
    background-color: {t.bg_main};
}}

QWidget {{
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    color: #E5E7EB;
}}

/* Card Containers */
QFrame#Card {{
    background-color: {t.bg_card};
    border: 1px solid {t.border};
    border-radius: 16px;
}}

QFrame#HeaderCard {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {t.bg_card}, stop:1 {t.bg_card_alt});
    border: 1px solid {t.border_soft};
    border-radius: 16px;
}}

QFrame#AccentBar {{
    background-color: {t.accent};
    border-radius: 2px;
}}

QLabel#HeaderLabel {{
    font-size: 16px;
    font-weight: 800;
    color: #F5F5F5;
    letter-spacing: 0.5px;
}}

QLabel#BrandLabel {{
    font-size: 19px;
    font-weight: 900;
    color: #FFFFFF;
    letter-spacing: 1px;
}}

QLabel#SubLabel {{
    font-size: 12px;
    color: #8B8F98;
}}

QLabel#Badge {{
    background-color: {t.bg_badge};
    color: #C9CDD4;
    font-size: 11px;
    font-weight: 700;
    border-radius: 10px;
    padding: 3px 10px;
    border: 1px solid {t.border_soft};
}}

/* Push Buttons */
QPushButton {{
    background-color: {t.bg_button};
    color: #E5E7EB;
    border: 1px solid {t.border_strong};
    border-radius: 9px;
    padding: 7px 16px;
    font-size: 13px;
    font-weight: 600;
}}

QPushButton:hover {{
    background-color: {t.bg_button_hover};
    border-color: {t.accent_dim};
}}

QPushButton:pressed {{
    background-color: {t.bg_button_pressed};
}}

QPushButton#PrimaryButton {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t.accent_light}, stop:1 {t.accent});
    color: {t.accent_text};
    border: none;
    padding: 11px 26px;
    font-size: 14px;
    font-weight: 800;
    border-radius: 9px;
}}

QPushButton#PrimaryButton:hover {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t.accent_light}, stop:1 {t.accent_light});
}}

QPushButton#PrimaryButton:disabled {{
    background-color: #33363C;
    color: #6B6F76;
}}

QPushButton#DangerButton {{
    background-color: #241417;
    color: #F87171;
    border: 1px solid #4A2126;
}}

QPushButton#DangerButton:hover {{
    background-color: #331A1E;
}}

QPushButton#AccentSwatchButton {{
    background-color: {t.accent};
    border: 2px solid {t.border_strong};
    border-radius: 17px;
    min-width: 34px;
    max-width: 34px;
    min-height: 34px;
    max-height: 34px;
    padding: 0px;
}}

QPushButton#AccentSwatchButton:hover {{
    border-color: #FFFFFF;
}}

/* List Widget (Left Side) */
QListWidget {{
    background-color: {t.bg_input};
    border: 1px solid {t.border};
    border-radius: 10px;
    outline: none;
    padding: 5px;
}}

QListWidget::item {{
    background-color: {t.bg_list_item};
    border: 1px solid {t.border};
    border-radius: 7px;
    margin-bottom: 4px;
    padding: 9px 12px;
    font-size: 13px;
    color: #DADCE0;
}}

QListWidget::item:hover {{
    background-color: {t.bg_list_item_hover};
    border-color: {t.border_strong};
}}

QListWidget::item:selected {{
    background-color: {t.bg_list_item_selected};
    border-color: {t.accent};
    color: #FFFFFF;
    font-weight: 600;
}}

/* Text Edit (Right Side) */
QTextEdit {{
    background-color: {t.bg_input};
    border: 1px solid {t.border};
    border-radius: 10px;
    padding: 11px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 13px;
    line-height: 1.4;
    color: #E5E7EB;
    selection-background-color: {t.accent_dim};
}}

QTextEdit:focus {{
    border: 1.5px solid {t.accent};
}}

QLineEdit {{
    background-color: {t.bg_input};
    border: 1px solid {t.border_strong};
    border-radius: 9px;
    padding: 10px 12px;
    font-size: 14px;
    color: #F5F5F5;
    selection-background-color: {t.accent_dim};
}}

QLineEdit:focus {{
    border: 1.5px solid {t.accent};
}}

/* Combo Box (e.g. Key Type dropdown) */
QComboBox {{
    background-color: #F5F5F5;
    color: #111111;
    border: 1px solid {t.border_strong};
    border-radius: 9px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 600;
}}

QComboBox:hover {{
    border-color: {t.accent_dim};
}}

QComboBox:focus {{
    border: 1.5px solid {t.accent};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox QAbstractItemView {{
    background-color: #F5F5F5;
    color: #111111;
    border: 1px solid {t.border_strong};
    selection-background-color: {t.accent_dim};
    selection-color: #111111;
    outline: none;
    padding: 4px;
}}

/* Spin Box (e.g. Quantity) */
QSpinBox {{
    background-color: #F5F5F5;
    color: #111111;
    border: 1px solid {t.border_strong};
    border-radius: 9px;
    padding: 8px 10px;
    font-size: 13px;
    font-weight: 600;
}}

QSpinBox:hover {{
    border-color: {t.accent_dim};
}}

QSpinBox:focus {{
    border: 1.5px solid {t.accent};
}}

QSpinBox::up-button, QSpinBox::down-button {{
    background-color: #E5E5E5;
    border: none;
    width: 18px;
}}

QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background-color: #D5D5D5;
}}

/* Table Widget (Live Preview) */
QTableWidget {{
    background-color: {t.bg_input};
    border: 1px solid {t.border};
    border-radius: 10px;
    gridline-color: {t.border};
    alternate-background-color: {t.bg_card};
}}

QHeaderView::section {{
    background-color: {t.bg_list_item};
    color: #B8BCC4;
    font-weight: 700;
    font-size: 12px;
    border: none;
    border-bottom: 1px solid {t.border};
    padding: 7px 10px;
}}

/* Tab Widget */
QTabWidget::pane {{
    background-color: transparent;
    border: none;
    top: -1px;
}}

QTabBar {{
    background-color: transparent;
    qproperty-drawBase: 0;
}}

QTabBar::tab {{
    background-color: {t.bg_card};
    color: #8B8F98;
    border: 1px solid {t.border};
    border-bottom: none;
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    padding: 9px 17px;
    margin-right: 5px;
    font-size: 13px;
    font-weight: 600;
}}

QTabBar::tab:hover {{
    background-color: {t.bg_button_hover};
    color: #F5F5F5;
}}

QTabBar::tab:selected {{
    background-color: {t.bg_card_alt};
    color: {t.accent};
    border-color: {t.accent_dim};
}}

QCheckBox {{
    font-size: 13px;
    color: #C9CDD4;
    spacing: 6px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {t.border_strong};
    border-radius: 4px;
    background-color: {t.bg_input};
}}

QCheckBox::indicator:checked {{
    background-color: {t.accent};
    border-color: {t.accent};
    image: url(none);
}}

QScrollBar:vertical {{
    background: {t.bg_input};
    width: 10px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {t.border_strong};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t.accent_dim};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
"""


def apply_glow(widget, color_hex: str, blur: int = 30, y_offset: int = 0, alpha: int = 160):
    """Attach (or refresh) a soft colored glow behind a widget."""
    effect = QGraphicsDropShadowEffect(widget)
    c = QColor(color_hex)
    c.setAlpha(alpha)
    effect.setColor(c)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    widget.setGraphicsEffect(effect)

class ReorderableDropListWidget(QListWidget):
    """
    QListWidget that supports BOTH dropping external files from Windows Explorer
    AND internal drag-and-drop item re-ordering, along with Ctrl+C / Ctrl+V / Ctrl+D duplication.
    """
    files_dropped = pyqtSignal(list)
    order_changed = pyqtSignal()
    copy_requested = pyqtSignal()
    paste_requested = pyqtSignal()
    duplicate_requested = pyqtSignal()
    delete_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls() or event.source() == self:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls() or event.source() == self:
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            paths = []
            for url in event.mimeData().urls():
                p = Path(url.toLocalFile())
                if p.exists():
                    if p.is_dir():
                        for child in sorted(p.iterdir()):
                            if child.is_file():
                                paths.append(child)
                    elif p.is_file():
                        paths.append(p)
            if paths:
                self.files_dropped.emit(paths)
        elif event.source() == self:
            super().dropEvent(event)
            self.order_changed.emit()
        else:
            super().dropEvent(event)

    def keyPressEvent(self,event):
        if event.matches(QKeySequence.Copy):
            self.copy_requested.emit()
        elif event.matches(QKeySequence.Paste):
            self.paste_requested.emit()
        elif event.key() == Qt.Key_D and event.modifiers() == Qt.ControlModifier:
            self.duplicate_requested.emit()
        elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_requested.emit()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        from PyQt5.QtWidgets import QMenu, QAction
        menu = QMenu(self)
        
        copy_act = QAction("📋 Copy Selected (Ctrl+C)", self)
        copy_act.triggered.connect(self.copy_requested.emit)
        
        paste_act = QAction("📋 Paste / Duplicate (Ctrl+V)", self)
        paste_act.triggered.connect(self.paste_requested.emit)

        dup_act = QAction("📄 Duplicate Selected (Ctrl+D)", self)
        dup_act.triggered.connect(self.duplicate_requested.emit)

        del_act = QAction("🗑 Remove Selected (Del)", self)
        del_act.triggered.connect(self.delete_requested.emit)

        menu.addAction(copy_act)
        menu.addAction(paste_act)
        menu.addAction(dup_act)
        menu.addSeparator()
        menu.addAction(del_act)
        menu.exec_(event.globalPos())



class LicenseDialog(QDialog):
    """
    Encrypted key-lock screen shown before the main tool is accessible.
    Keys are produced by the companion 'Offset Key Generator' (keygen.py)
    and validated locally via an HMAC-SHA256 signature (see license_core.py).
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Offset Auto Renamer — Activation")
        self.setFixedSize(440, 710)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.unlocked = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 26)
        layout.setSpacing(14)

        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        base_dir = Path(__file__).parent
        png_file = base_dir / "illust.png"
        if png_file.exists():
            pixmap = QPixmap(str(png_file)).scaled(
                90, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            logo_label.setPixmap(pixmap)
        layout.addWidget(logo_label)

        brand = QLabel("OFFSET AUTO RENAMER")
        brand.setObjectName("BrandLabel")
        brand.setAlignment(Qt.AlignCenter)
        layout.addWidget(brand)

        subtitle = QLabel("Enter your license key to unlock the tool")
        subtitle.setObjectName("SubLabel")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        layout.addSpacing(8)

        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("OFST-XXXX-XXXX-XXXX-XXXX")
        self.key_input.setAlignment(Qt.AlignCenter)
        self.key_input.textChanged.connect(self._format_key_input)
        self.key_input.returnPressed.connect(self.try_unlock)
        layout.addWidget(self.key_input)

        hwid_input_label = QLabel("Your System ID (copy it from below, then paste it here)")
        hwid_input_label.setObjectName("SubLabel")
        hwid_input_label.setAlignment(Qt.AlignCenter)
        hwid_input_label.setWordWrap(True)
        layout.addWidget(hwid_input_label)

        self.hwid_input = QLineEdit()
        self.hwid_input.setPlaceholderText("XXXX-XXXX-XXXX")
        self.hwid_input.setAlignment(Qt.AlignCenter)
        self.hwid_input.textChanged.connect(self._format_hwid_input)
        self.hwid_input.returnPressed.connect(self.try_unlock)
        layout.addWidget(self.hwid_input)

        self.status_label = QLabel(" ")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 12px; font-weight: 700;")
        layout.addWidget(self.status_label)

        self.remember_checkbox = QCheckBox("Remember this key on this device")
        self.remember_checkbox.setChecked(True)
        layout.addWidget(self.remember_checkbox, alignment=Qt.AlignCenter)

        layout.addSpacing(4)

        self.unlock_btn = QPushButton("🔓  Unlock")
        self.unlock_btn.setObjectName("PrimaryButton")
        self.unlock_btn.clicked.connect(self.try_unlock)
        layout.addWidget(self.unlock_btn)

        hint = QLabel("Don't Have a license key? Purchase one at Offset Shop Today!")
        hint.setObjectName("SubLabel")
        hint.setAlignment(Qt.AlignCenter)
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addSpacing(6)

        # System ID (HWID) card — share this with whoever issued the key so
        # they can record it against your key in their Key Log.
        hwid_card = QFrame()
        hwid_card.setObjectName("Card")
        hwid_layout = QVBoxLayout(hwid_card)
        hwid_layout.setContentsMargins(16, 13, 16, 13)
        hwid_layout.setSpacing(8)

        hwid_title = QLabel("YOUR SYSTEM ID")
        hwid_title.setAlignment(Qt.AlignCenter)
        hwid_title.setStyleSheet("font-size: 10px; font-weight: 800; color: #8B8F98; letter-spacing: 1px;")
        hwid_layout.addWidget(hwid_title)

        self._hwid_value = license_core.get_hwid()
        hwid_value_label = QLabel(self._hwid_value)
        hwid_value_label.setAlignment(Qt.AlignCenter)
        hwid_value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        hwid_value_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #F5F5F5; "
            "font-family: 'Consolas', 'Courier New', monospace; letter-spacing: 1px;"
        )
        hwid_layout.addWidget(hwid_value_label)

        hwid_desc = QLabel("Send this to whoever issued your key if they need it to track your license.")
        hwid_desc.setAlignment(Qt.AlignCenter)
        hwid_desc.setWordWrap(True)
        hwid_desc.setStyleSheet("font-size: 10px; color: #8B8F98;")
        hwid_layout.addWidget(hwid_desc)

        copy_hwid_btn = QPushButton("📋 Copy System ID")
        copy_hwid_btn.clicked.connect(lambda: QApplication.clipboard().setText(self._hwid_value))
        hwid_layout.addWidget(copy_hwid_btn)

        layout.addWidget(hwid_card)

        # Pre-fill a previously-saved valid key, if any.
        saved = license_core.load_saved_key()
        if saved:
            self.key_input.setText(saved)

    def _format_key_input(self, text: str):
        cleaned = text.upper()
        cursor_at_end = self.key_input.cursorPosition() == len(text)
        self.key_input.blockSignals(True)
        self.key_input.setText(cleaned)
        if cursor_at_end:
            self.key_input.setCursorPosition(len(cleaned))
        self.key_input.blockSignals(False)

    def _format_hwid_input(self, text: str):
        cleaned = text.upper()
        cursor_at_end = self.hwid_input.cursorPosition() == len(text)
        self.hwid_input.blockSignals(True)
        self.hwid_input.setText(cleaned)
        if cursor_at_end:
            self.hwid_input.setCursorPosition(len(cleaned))
        self.hwid_input.blockSignals(False)

    def try_unlock(self):
        key = self.key_input.text().strip()
        if not license_core.is_valid_key(key):
            self.status_label.setText("✗ Invalid key — please check and try again")
            self.status_label.setStyleSheet(f"color: {DANGER}; font-size: 12px; font-weight: 700;")
            return

        entered_hwid = self.hwid_input.text().strip().upper()
        actual_hwid = license_core.get_hwid()
        if not entered_hwid:
            self.status_label.setText("✗ Paste your System ID below — copy it from the card underneath")
            self.status_label.setStyleSheet(f"color: {DANGER}; font-size: 12px; font-weight: 700;")
            return
        if entered_hwid != actual_hwid:
            self.status_label.setText("✗ That System ID doesn't match this device")
            self.status_label.setStyleSheet(f"color: {DANGER}; font-size: 12px; font-weight: 700;")
            return

        if license_core.is_key_expired(key):
            expiry = license_core.get_key_expiry_date(key)
            self.status_label.setText(
                f"✗ This key expired on {expiry.isoformat()} — get a new 1-month or lifetime key"
            )
            self.status_label.setStyleSheet(f"color: {DANGER}; font-size: 12px; font-weight: 700;")
            return

        self.status_label.setText("Checking key…")
        self.status_label.setStyleSheet(f"color: {theme.accent_dim}; font-size: 12px; font-weight: 700;")
        self.unlock_btn.setEnabled(False)
        QApplication.processEvents()

        revoked = license_core.is_key_revoked(key)
        self.unlock_btn.setEnabled(True)

        if revoked:
            self.status_label.setText("✗ This key has been deactivated")
            self.status_label.setStyleSheet(f"color: {DANGER}; font-size: 12px; font-weight: 700;")
            return

        self.unlocked = True
        if self.remember_checkbox.isChecked():
            license_core.save_key(key)
        self.status_label.setText(f"✓ Key accepted ({license_core.describe_key(key)})")
        self.status_label.setStyleSheet(f"color: {SUCCESS}; font-size: 12px; font-weight: 700;")
        self.accept()


class _RevocationCheckWorker(QThread):
    """
    Runs a single (possibly network-hitting) revocation check off the
    GUI thread, so the periodic live check never freezes the app.
    """
    checked = pyqtSignal(bool)  # True if the key is revoked

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self._key = key

    def run(self):
        try:
            revoked = license_core.is_key_revoked(self._key, force=True)
        except Exception:
            revoked = False  # never lock someone out due to a local error
        self.checked.emit(revoked)


class _UpdateCheckWorker(QThread):
    """
    Checks the public releases repo for a newer version and, if found,
    downloads it in the background -- entirely off the GUI thread so it
    never interrupts whatever the person is doing. See updater.py.
    """
    update_ready = pyqtSignal(str)  # path to the downloaded new .exe

    def run(self):
        try:
            new_exe_path = updater.check_and_download_update()
        except Exception:
            new_exe_path = None
        if new_exe_path:
            self.update_ready.emit(str(new_exe_path))


class AccentPickerDialog(QDialog):
    """
    Lets the user pick an accent color -- either from a curated preset grid
    or a full custom color picker. The chosen color drives every accent
    highlight in the app AND subtly retints all of the dark backgrounds,
    so this one control effectively lets you recolor the whole theme.
    """
    def __init__(self, current_hex: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Accent Color")
        self.setFixedSize(360, 300)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.chosen_hex = current_hex

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Pick an accent color")
        title.setObjectName("HeaderLabel")
        layout.addWidget(title)

        subtitle = QLabel("This also retints the background to match.")
        subtitle.setObjectName("SubLabel")
        layout.addWidget(subtitle)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)

        all_swatches = list(ACCENT_PRESETS)
        if not any(hex_val.lower() == current_hex.lower() for _, hex_val in all_swatches):
            all_swatches = [("Current", current_hex)] + all_swatches

        for i, (label, hex_val) in enumerate(all_swatches):
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setFixedSize(60, 44)
            btn.setCursor(QCursor(Qt.PointingHandCursor))
            btn.setToolTip(f"{label} ({hex_val})")
            btn.setChecked(hex_val.lower() == current_hex.lower())
            btn.setStyleSheet(self._swatch_style(hex_val, btn.isChecked()))
            btn.clicked.connect(lambda _checked, h=hex_val, b=btn: self._select_preset(h, b))
            self.button_group.addButton(btn)
            grid.addWidget(btn, i // 4, i % 4)
        layout.addLayout(grid)

        self._preset_buttons = self.button_group.buttons()

        custom_row = QHBoxLayout()
        self.preview_swatch = QLabel()
        self.preview_swatch.setFixedSize(28, 28)
        custom_row.addWidget(self.preview_swatch)

        self.hex_label = QLabel(current_hex.upper())
        self.hex_label.setObjectName("SubLabel")
        custom_row.addWidget(self.hex_label)
        custom_row.addStretch()

        custom_btn = QPushButton("🎨 Custom…")
        custom_btn.clicked.connect(self._pick_custom)
        custom_row.addWidget(custom_btn)
        layout.addLayout(custom_row)

        self._update_preview()

        layout.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _swatch_style(self, hex_val: str, checked: bool) -> str:
        border = "#FFFFFF" if checked else "#3A3D44"
        width = 3 if checked else 1
        return (
            f"background-color: {hex_val}; border-radius: 8px; "
            f"border: {width}px solid {border};"
        )

    def _select_preset(self, hex_val: str, clicked_btn: QPushButton):
        self.chosen_hex = hex_val
        for btn in self._preset_buttons:
            is_this = btn is clicked_btn
            btn.setChecked(is_this)
            tip = btn.toolTip()
            swatch_hex = tip.split("(")[-1].rstrip(")")
            btn.setStyleSheet(self._swatch_style(swatch_hex, is_this))
        self._update_preview()

    def _pick_custom(self):
        color = QColorDialog.getColor(QColor(self.chosen_hex), self, "Choose Accent Color")
        if color.isValid():
            for btn in self._preset_buttons:
                btn.setChecked(False)
            self.chosen_hex = color.name()
            self._update_preview()

    def _update_preview(self):
        self.preview_swatch.setStyleSheet(
            f"background-color: {self.chosen_hex}; border-radius: 6px; border: 1px solid #3A3D44;"
        )
        self.hex_label.setText(self.chosen_hex.upper())


class AutoRenamerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Offset Auto Renamer")
        self.resize(1100, 720)
        self.setMinimumSize(900, 600)

        app_icon = load_multi_res_icon()
        self.setWindowIcon(app_icon)

        # Store loaded file paths in current order
        self.loaded_files = [] # list of Path objects
        self.last_renamed_history = [] # For Undo functionality
        self.internal_copied_paths = [] # For Ctrl+C / Ctrl+V item duplication

        self.init_ui()
        self.setStyleSheet(build_stylesheet(theme))
        apply_glow(self.accent_btn, theme.accent, blur=22, alpha=190)
        apply_glow(self.apply_btn, theme.accent, blur=26, y_offset=2, alpha=140)

        # --- Live license revocation watch ---
        # Periodically re-checks (in the background) whether the key this
        # session is using has been deactivated, and immediately locks the
        # tool out if so — no need to wait for the app to be restarted.
        self._revocation_worker = None
        self._revocation_lockout_active = False
        self.revocation_timer = QTimer(self)
        self.revocation_timer.timeout.connect(self._start_live_revocation_check)
        self.revocation_timer.start(license_core.LIVE_REVOCATION_CHECK_INTERVAL * 1000)

        # --- Silent auto-update ---
        # Checks the public releases repo once on launch. If a newer build
        # exists, it downloads in the background with zero interruption; the
        # swap happens automatically the next time the app closes normally.
        self._pending_update_exe = None
        self._update_worker = None
        QTimer.singleShot(3000, self._start_update_check)

    def _start_update_check(self):
        if self._update_worker is not None and self._update_worker.isRunning():
            return
        self._update_worker = _UpdateCheckWorker(self)
        self._update_worker.update_ready.connect(self._on_update_ready)
        self._update_worker.start()

    def _on_update_ready(self, new_exe_path: str):
        # Nothing visible happens here on purpose — the update is simply
        # queued to apply itself the next time the app is closed normally.
        self._pending_update_exe = new_exe_path

    def closeEvent(self, event):
        if self._pending_update_exe:
            try:
                updater.prepare_and_launch_swap(self._pending_update_exe)
            except Exception:
                pass  # never block the user from closing over an update hiccup
        super().closeEvent(event)

    def _start_live_revocation_check(self):
        if self._revocation_lockout_active:
            return  # already locked out / dialog open — nothing more to do
        key = license_core.load_saved_key()
        if not key:
            return
        # Expiry is local (no network), so check it immediately rather than
        # waiting on the background worker below.
        if license_core.is_key_expired(key):
            self._lock_out_due_to_revocation(expired=True)
            return
        if self._revocation_worker is not None and self._revocation_worker.isRunning():
            return  # a check is already in flight, skip this tick
        self._revocation_worker = _RevocationCheckWorker(key, self)
        self._revocation_worker.checked.connect(self._on_live_revocation_result)
        self._revocation_worker.start()

    def _on_live_revocation_result(self, revoked: bool):
        if revoked and not self._revocation_lockout_active:
            self._lock_out_due_to_revocation()

    def _lock_out_due_to_revocation(self, expired: bool = False):
        """
        Called the moment a background check discovers the active key has
        been deactivated (or, locally, that a 1-month key has expired).
        Immediately hides the tool and forces the activation screen, with
        an option to enter a new key without restarting the app.
        """
        self._revocation_lockout_active = True
        self.revocation_timer.stop()
        license_core.clear_saved_key()

        if expired:
            QMessageBox.warning(
                self,
                "Key Expired",
                "Your 1-month license key has expired.\n\n"
                "You'll need to enter a new key to keep using Offset Auto Renamer."
            )
        else:
            QMessageBox.warning(
                self,
                "Access Revoked",
                "Your license key has been deactivated by the seller.\n\n"
                "You'll need to enter a new key to keep using Offset Auto Renamer."
            )

        self.hide()
        while True:
            gate = LicenseDialog(self)
            gate.setWindowIcon(self.windowIcon())
            result = gate.exec_()
            if result == QDialog.Accepted and gate.unlocked:
                self._revocation_lockout_active = False
                self.revocation_timer.start(license_core.LIVE_REVOCATION_CHECK_INTERVAL * 1000)
                self.show()
                return
            else:
                # User closed/cancelled the activation screen — exit the app
                # rather than leaving a locked, unusable window around.
                QApplication.quit()
                return

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Top Header Bar
        header_frame = QFrame()
        header_frame.setObjectName("HeaderCard")
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(18, 14, 18, 14)

        logo_label = QLabel()
        base_dir = Path(__file__).parent
        png_file = base_dir / "illust.png"
        if png_file.exists():
            pixmap = QPixmap(str(png_file)).scaled(
                44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            logo_label.setPixmap(pixmap)
        header_layout.addWidget(logo_label)
        header_layout.addSpacing(12)

        title_vbox = QVBoxLayout()
        title_label = QLabel("OFFSET AUTO RENAMER")
        title_label.setObjectName("BrandLabel")
        sub_label = QLabel("Drag files to reorder on the left • Paste new names line-by-line on the right")
        sub_label.setObjectName("SubLabel")
        title_vbox.addWidget(title_label)
        title_vbox.addWidget(sub_label)
        accent_bar = QFrame()
        accent_bar.setObjectName("AccentBar")
        accent_bar.setFixedHeight(3)
        accent_bar.setFixedWidth(46)
        title_vbox.addWidget(accent_bar)
        header_layout.addLayout(title_vbox)

        header_layout.addStretch()

        self.accent_btn = QPushButton()
        self.accent_btn.setObjectName("AccentSwatchButton")
        self.accent_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.accent_btn.setToolTip("Change accent color (also retints the background)")
        self.accent_btn.clicked.connect(self.open_accent_picker)
        header_layout.addWidget(self.accent_btn)
        header_layout.addSpacing(10)

        self.undo_button = QPushButton("↩ Undo Last Rename")
        self.undo_button.setEnabled(False)
        self.undo_button.clicked.connect(self.undo_last_rename)
        header_layout.addWidget(self.undo_button)

        main_layout.addWidget(header_frame)

        # Main Splitter (Left: Files List, Right: Textbox)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(10)

        # ---------------- LEFT PANEL: FILE LIST ----------------
        left_card = QFrame()
        left_card.setObjectName("Card")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(14, 14, 14, 14)

        left_header = QHBoxLayout()
        left_title = QLabel("1. Target Files (Drag to re-order)")
        left_title.setObjectName("HeaderLabel")
        self.file_count_badge = QLabel("0 files")
        self.file_count_badge.setObjectName("Badge")
        left_header.addWidget(left_title)
        left_header.addWidget(self.file_count_badge)
        left_header.addStretch()

        add_files_btn = QPushButton("+ Add Files")
        add_files_btn.clicked.connect(self.browse_files)
        clear_files_btn = QPushButton("Clear")
        clear_files_btn.setObjectName("DangerButton")
        clear_files_btn.clicked.connect(self.clear_files)
        left_header.addWidget(add_files_btn)
        left_header.addWidget(clear_files_btn)

        left_layout.addLayout(left_header)

        # Dropzone / List Widget
        self.file_list_widget = ReorderableDropListWidget()
        self.file_list_widget.files_dropped.connect(self.add_files)
        self.file_list_widget.order_changed.connect(self.on_file_order_changed)
        self.file_list_widget.copy_requested.connect(self.copy_selected_files)
        self.file_list_widget.paste_requested.connect(self.paste_files)
        self.file_list_widget.duplicate_requested.connect(self.duplicate_selected_files)
        self.file_list_widget.delete_requested.connect(self.delete_selected_files)
        left_layout.addWidget(self.file_list_widget)

        hint_label = QLabel("💡 Tip: You can drag files directly from Windows Explorer into this list.")
        hint_label.setObjectName("SubLabel")
        left_layout.addWidget(hint_label)

        splitter.addWidget(left_card)

        # ---------------- RIGHT PANEL: NEW NAMES TEXTBOX ----------------
        right_card = QFrame()
        right_card.setObjectName("Card")
        right_layout = QVBoxLayout(right_card)
        right_layout.setContentsMargins(14, 14, 14, 14)

        right_header = QHBoxLayout()
        right_title = QLabel("2. New Filenames (One per line)")
        right_title.setObjectName("HeaderLabel")
        self.line_count_badge = QLabel("0 lines")
        self.line_count_badge.setObjectName("Badge")
        right_header.addWidget(right_title)
        right_header.addWidget(self.line_count_badge)
        right_header.addStretch()

        paste_sample_btn = QPushButton("Load Sample")
        paste_sample_btn.clicked.connect(self.load_sample_names)
        clear_text_btn = QPushButton("Clear")
        clear_text_btn.setObjectName("DangerButton")
        clear_text_btn.clicked.connect(self.clear_names_text)
        right_header.addWidget(paste_sample_btn)
        right_header.addWidget(clear_text_btn)

        right_layout.addLayout(right_header)

        self.names_text_edit = QTextEdit()
        self.names_text_edit.setPlaceholderText(
            "Paste or type your new names here, one per line:\n\n"
            "Blank_1\n"
            "Blank_2\n"
            "Blank_3\n"
            "Blank_4"
        )
        self.names_text_edit.textChanged.connect(self.on_names_text_changed)
        right_layout.addWidget(self.names_text_edit)

        right_hint = QLabel("💡 New names correspond 1-to-1 with the file order on the left.")
        right_hint.setObjectName("SubLabel")
        right_layout.addWidget(right_hint)

        splitter.addWidget(right_card)
        splitter.setSizes([500, 500])

        main_layout.addWidget(splitter, stretch=1)

        # ---------------- LIVE PREVIEW TABLE ----------------
        preview_card = QFrame()
        preview_card.setObjectName("Card")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(14, 12, 14, 12)

        prev_header = QHBoxLayout()
        prev_title = QLabel("3. Live Rename Mapping Preview")
        prev_title.setObjectName("HeaderLabel")
        prev_header.addWidget(prev_title)
        prev_header.addStretch()

        self.ext_checkbox = QCheckBox("Preserve original file extension automatically")
        self.ext_checkbox.setChecked(True)
        self.ext_checkbox.stateChanged.connect(self.update_preview)
        prev_header.addWidget(self.ext_checkbox)

        preview_layout.addLayout(prev_header)

        self.preview_table = QTableWidget(0, 4)
        self.preview_table.setHorizontalHeaderLabels(["#", "Original Filename", "⟶  New Filename", "Status"])
        self.preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.preview_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.preview_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.preview_table.setAlternatingRowColors(True)
        self.preview_table.setMaximumHeight(160)
        preview_layout.addWidget(self.preview_table)

        main_layout.addWidget(preview_card)

        # ---------------- BOTTOM ACTION BAR ----------------
        bottom_layout = QHBoxLayout()

        self.status_bar_label = QLabel("Ready. Drag files to begin.")
        self.status_bar_label.setObjectName("SubLabel")
        bottom_layout.addWidget(self.status_bar_label)

        bottom_layout.addStretch()

        self.apply_btn = QPushButton("🚀 Apply File Renaming")
        self.apply_btn.setObjectName("PrimaryButton")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.apply_renaming)
        bottom_layout.addWidget(self.apply_btn)

        main_layout.addLayout(bottom_layout)

    # ---------------- APPEARANCE / ACCENT COLOR ----------------
    def open_accent_picker(self):
        dialog = AccentPickerDialog(theme.accent, self)
        if dialog.exec_() == QDialog.Accepted and dialog.chosen_hex:
            self.apply_accent(dialog.chosen_hex)

    def apply_accent(self, hex_color: str):
        theme.set_accent(hex_color)
        save_accent(theme.accent)
        stylesheet = build_stylesheet(theme)
        QApplication.instance().setStyleSheet(stylesheet)
        self.setStyleSheet(stylesheet)
        apply_glow(self.accent_btn, theme.accent, blur=22, alpha=190)
        apply_glow(self.apply_btn, theme.accent, blur=26, y_offset=2, alpha=140)
        self.status_bar_label.setText(f"Accent color updated to {theme.accent}.")

    # ---------------- FILE HANDLING LOGIC ----------------
    def browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Files to Rename")
        if files:
            self.add_files([Path(f) for f in files])

    def add_files(self, paths: list[Path]):
        existing_paths = set(self.loaded_files)
        added_any = False
        for p in paths:
            if p not in existing_paths and p.exists() and p.is_file():
                self.loaded_files.append(p)
                existing_paths.add(p)
                added_any = True
        
        if added_any:
            self.refresh_file_list_widget()
            self.update_preview()

    def refresh_file_list_widget(self):
        self.file_list_widget.blockSignals(True)
        self.file_list_widget.clear()
        for idx, file_path in enumerate(self.loaded_files, 1):
            item = QListWidgetItem(f"≡  {idx}. {file_path.name}")
            item.setData(Qt.UserRole, str(file_path))
            item.setToolTip(str(file_path))
            self.file_list_widget.addItem(item)
        self.file_list_widget.blockSignals(False)
        self.file_count_badge.setText(f"{len(self.loaded_files)} files")

    def clear_files(self):
        self.loaded_files.clear()
        self.refresh_file_list_widget()
        self.update_preview()

    def on_file_order_changed(self):
        # Sync self.loaded_files with QListWidget current order
        new_order = []
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            file_path_str = item.data(Qt.UserRole)
            if file_path_str:
                new_order.append(Path(file_path_str))
        
        self.loaded_files = new_order
        self.refresh_file_list_widget()
        self.update_preview()

    # ---------------- COPY / PASTE / DUPLICATE / DELETE ----------------
    def _get_unique_duplicate_path(self, src_path: Path) -> Path:
        """
        Generates a non-conflicting filename for physical disk duplication in the file's folder.
        E.g. photo.jpg -> photo - Copy.jpg -> photo - Copy (2).jpg
        """
        parent = src_path.parent
        stem = src_path.stem
        ext = src_path.suffix

        candidate = parent / f"{stem} - Copy{ext}"
        if not candidate.exists():
            return candidate

        counter = 2
        while True:
            candidate = parent / f"{stem} - Copy ({counter}){ext}"
            if not candidate.exists():
                return candidate
            counter += 1

    def duplicate_paths_on_disk(self, sources: list[Path]) -> list[Path]:
        created_paths = []
        for src in sources:
            if not src.exists() or not src.is_file():
                continue
            dest = self._get_unique_duplicate_path(src)
            try:
                shutil.copy2(src, dest)
                created_paths.append(dest)
            except Exception as e:
                print(f"Error copying {src}: {e}")
        return created_paths

    def copy_selected_files(self):
        selected_items = self.file_list_widget.selectedItems()
        if not selected_items:
            return
        
        self.internal_copied_paths = []
        path_strings = []
        for item in selected_items:
            path_str = item.data(Qt.UserRole)
            if path_str:
                p = Path(path_str)
                if p.exists():
                    self.internal_copied_paths.append(p)
                    path_strings.append(str(p))

        if path_strings:
            QApplication.clipboard().setText("\n".join(path_strings))
            self.status_bar_label.setText(f"Copied {len(self.internal_copied_paths)} file path(s) to clipboard. Press Ctrl+V to duplicate on disk.")

    def paste_files(self):
        sources = []

        # 1. Use internal clipboard if available
        if self.internal_copied_paths:
            sources.extend(self.internal_copied_paths)
        else:
            # 2. Check system clipboard MIME data
            cb_mime = QApplication.clipboard().mimeData()
            if cb_mime.hasUrls():
                for url in cb_mime.urls():
                    p = Path(url.toLocalFile())
                    if p.exists() and p.is_file():
                        sources.append(p)
            elif cb_mime.hasText():
                for line in cb_mime.text().splitlines():
                    cleaned = line.strip('"\' ')
                    if cleaned:
                        p = Path(cleaned)
                        if p.exists() and p.is_file():
                            sources.append(p)

        if sources:
            # Physically duplicate files on disk in their directory!
            new_copies = self.duplicate_paths_on_disk(sources)
            if new_copies:
                self.loaded_files.extend(new_copies)
                self.refresh_file_list_widget()
                self.update_preview()
                self.status_bar_label.setText(f"Created {len(new_copies)} physical copy file(s) on disk.")

    def duplicate_selected_files(self):
        selected_items = self.file_list_widget.selectedItems()
        if not selected_items:
            return
        
        sources = []
        for item in selected_items:
            path_str = item.data(Qt.UserRole)
            if path_str:
                sources.append(Path(path_str))

        if sources:
            # Physically duplicate files on disk in their directory!
            new_copies = self.duplicate_paths_on_disk(sources)
            if new_copies:
                self.loaded_files.extend(new_copies)
                self.refresh_file_list_widget()
                self.update_preview()
                self.status_bar_label.setText(f"Created {len(new_copies)} physical copy file(s) on disk.")

    def delete_selected_files(self):
        selected_items = self.file_list_widget.selectedItems()
        if not selected_items:
            return

        to_remove = set()
        for item in selected_items:
            path_str = item.data(Qt.UserRole)
            if path_str:
                to_remove.add(path_str)

        new_files = [p for p in self.loaded_files if str(p) not in to_remove]
        self.loaded_files = new_files
        self.refresh_file_list_widget()
        self.update_preview()
        self.status_bar_label.setText("Removed selected file(s) from list.")

    # ---------------- TEXT HANDLING LOGIC ----------------
    def on_names_text_changed(self):
        lines = [line.strip() for line in self.names_text_edit.toPlainText().splitlines() if line.strip()]
        self.line_count_badge.setText(f"{len(lines)} lines")
        self.update_preview()

    def clear_names_text(self):
        self.names_text_edit.clear()
        self.update_preview()

    def load_sample_names(self):
        sample = "\n".join([f"Blank_{i}" for i in range(1, len(self.loaded_files) + 1 if self.loaded_files else 5)])
        self.names_text_edit.setPlainText(sample)

    # ---------------- LIVE PREVIEW GENERATION ----------------
    def update_preview(self):
        self.preview_table.setRowCount(0)
        raw_lines = [line.strip() for line in self.names_text_edit.toPlainText().splitlines() if line.strip()]
        preserve_ext = self.ext_checkbox.isChecked()

        can_rename = len(self.loaded_files) > 0 and len(raw_lines) > 0

        target_names_used = set()
        has_errors = False

        for idx, file_path in enumerate(self.loaded_files):
            orig_name = file_path.name
            orig_ext = file_path.suffix

            if idx < len(raw_lines):
                new_input = raw_lines[idx]
                target_path = Path(new_input)

                if preserve_ext and not target_path.suffix and orig_ext:
                    new_name = new_input + orig_ext
                else:
                    new_name = new_input
                
                # Check status
                if new_name == orig_name:
                    status = "Unchanged"
                    status_color = "#718096"
                elif new_name in target_names_used:
                    status = "⚠️ Duplicate target"
                    status_color = "#DD6B20"
                    has_errors = True
                elif (file_path.parent / new_name).exists() and new_name.lower() != orig_name.lower():
                    status = "⚠️ Existing file conflict"
                    status_color = "#E53E3E"
                    has_errors = True
                else:
                    status = "Ready ✓"
                    status_color = "#38A169"

                target_names_used.add(new_name)
            else:
                new_name = "(No name provided)"
                status = "Missing target line"
                status_color = "#A0AEC0"

            row_idx = self.preview_table.rowCount()
            self.preview_table.insertRow(row_idx)

            idx_item = QTableWidgetItem(str(idx + 1))
            idx_item.setTextAlignment(Qt.AlignCenter)
            
            orig_item = QTableWidgetItem(orig_name)
            new_item = QTableWidgetItem(new_name)

            status_item = QTableWidgetItem(status)
            status_item.setForeground(QColor(status_color))
            status_item.setFont(QFont("Segoe UI", 9, QFont.Bold))

            self.preview_table.setItem(row_idx, 0, idx_item)
            self.preview_table.setItem(row_idx, 1, orig_item)
            self.preview_table.setItem(row_idx, 2, new_item)
            self.preview_table.setItem(row_idx, 3, status_item)

        if can_rename and not has_errors:
            self.apply_btn.setEnabled(True)
            self.status_bar_label.setText(f"Ready to rename {min(len(self.loaded_files), len(raw_lines))} file(s).")
        else:
            self.apply_btn.setEnabled(False)
            if len(self.loaded_files) == 0:
                self.status_bar_label.setText("Please add target files.")
            elif len(raw_lines) == 0:
                self.status_bar_label.setText("Please enter new names on the right side.")
            elif has_errors:
                self.status_bar_label.setText("Please resolve duplicate or conflicting filenames before renaming.")

    # ---------------- APPLY RENAMING LOGIC ----------------
    def apply_renaming(self):
        raw_lines = [line.strip() for line in self.names_text_edit.toPlainText().splitlines() if line.strip()]
        preserve_ext = self.ext_checkbox.isChecked()

        renamed_pairs = []
        failed_count = 0

        for idx, file_path in enumerate(self.loaded_files):
            if idx >= len(raw_lines):
                break
            
            orig_name = file_path.name
            orig_ext = file_path.suffix
            new_input = raw_lines[idx]
            target_path = Path(new_input)

            if preserve_ext and not target_path.suffix and orig_ext:
                new_name = new_input + orig_ext
            else:
                new_name = new_input

            target_file_path = file_path.parent / new_name

            if target_file_path == file_path:
                continue

            try:
                file_path.rename(target_file_path)
                renamed_pairs.append((file_path, target_file_path))
            except Exception as e:
                failed_count += 1

        if renamed_pairs:
            self.last_renamed_history = renamed_pairs
            self.undo_button.setEnabled(True)

            # Update loaded_files to reflect new paths
            renamed_dict = {old_p: new_p for old_p, new_p in renamed_pairs}
            self.loaded_files = [renamed_dict.get(p, p) for p in self.loaded_files]
            
            self.refresh_file_list_widget()
            self.update_preview()

            QMessageBox.information(
                self, "Success",
                f"Successfully renamed {len(renamed_pairs)} file(s)!"
                + (f"\n{failed_count} failed." if failed_count else "")
            )
        elif failed_count:
            QMessageBox.warning(self, "Error", f"Failed to rename files. Errors encountered: {failed_count}")

    # ---------------- UNDO RENAMING LOGIC ----------------
    def undo_last_rename(self):
        if not self.last_renamed_history:
            return

        reverted_count = 0
        reverted_dict = {}

        for old_p, new_p in self.last_renamed_history:
            if new_p.exists():
                try:
                    new_p.rename(old_p)
                    reverted_dict[new_p] = old_p
                    reverted_count += 1
                except Exception:
                    pass

        self.last_renamed_history = []
        self.undo_button.setEnabled(False)

        # Update loaded_files
        self.loaded_files = [reverted_dict.get(p, p) for p in self.loaded_files]
        self.refresh_file_list_widget()
        self.update_preview()

        QMessageBox.information(self, "Undo Complete", f"Reverted {reverted_count} file rename(s).")


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(build_stylesheet(theme))
    app_icon = load_multi_res_icon()
    app.setWindowIcon(app_icon)

    # Encrypted key-lock gate: must enter a valid, generated key to proceed.
    if not license_core.has_valid_saved_license():
        gate = LicenseDialog()
        gate.setWindowIcon(app_icon)
        if gate.exec_() != QDialog.Accepted or not gate.unlocked:
            sys.exit(0)

    window = AutoRenamerWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
