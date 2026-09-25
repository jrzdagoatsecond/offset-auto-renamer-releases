import sys
import ctypes
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QFrame, QSpinBox, QListWidget,
    QListWidgetItem, QMessageBox, QDialog, QFormLayout, QDialogButtonBox,
    QMenu, QAction, QComboBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QInputDialog
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QPixmap

import license_core
import revocation_admin
import key_log

try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Offset.KeyGenerator.GUI.1")
except Exception:
    pass


def load_multi_res_icon() -> QIcon:
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


# Reuse the exact same dark theme as the main app for a consistent look.
from app import build_stylesheet, theme, SUCCESS, DANGER  # noqa: E402


class RevocationSettingsDialog(QDialog):
    """
    One-time setup for where the revoked-keys list lives, and the
    Personal Access Token used to push updates to it. Stored locally
    only (keygen_config.json) — never bundled into the distributed app.

    Uses a GitHub Gist (a small standalone public snippet) rather than a
    file inside your main repo, so this keeps working even if your
    source-code repo is private — raw.githubusercontent.com can't serve
    private-repo files to the app (which has no token), but a public
    gist is readable by anyone with the link, with no auth needed.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Deactivation Settings")
        self.setMinimumWidth(460)

        cfg = revocation_admin.load_config()

        layout = QVBoxLayout(self)
        info = QLabel(
            "The revoked-keys list is hosted as a public GitHub Gist — a "
            "small, separate, standalone snippet. This works even if your "
            "main source-code repo is private, since the gist only ever "
            "stores key strings, never your secret."
        )
        info.setWordWrap(True)
        info.setObjectName("SubLabel")
        layout.addWidget(info)

        form = QFormLayout()
        self.token_input = QLineEdit(cfg.get("token", ""))
        self.token_input.setEchoMode(QLineEdit.Password)
        self.token_input.setPlaceholderText("GitHub personal access token (gist scope)")
        self.gist_id_input = QLineEdit(cfg.get("gist_id", ""))
        self.gist_id_input.setPlaceholderText("Filled in automatically once created")
        self.filename_input = QLineEdit(cfg.get("filename", "revoked_keys.json"))

        form.addRow("Access token:", self.token_input)
        form.addRow("Gist ID:", self.gist_id_input)
        form.addRow("Filename:", self.filename_input)
        layout.addLayout(form)

        token_hint = QLabel(
            "Create a token at github.com/settings/tokens (classic) with "
            "the 'gist' scope checked. Keep it secret — anyone with it can "
            "create/edit gists on your account."
        )
        token_hint.setWordWrap(True)
        token_hint.setObjectName("SubLabel")
        layout.addWidget(token_hint)

        create_row = QHBoxLayout()
        self.create_gist_btn = QPushButton("✨ Create New Gist")
        self.create_gist_btn.clicked.connect(self._create_gist)
        create_row.addWidget(self.create_gist_btn)
        create_row.addStretch()
        layout.addLayout(create_row)

        self.create_status = QLabel(" ")
        self.create_status.setWordWrap(True)
        self.create_status.setStyleSheet("font-size: 12px; font-weight: 700;")
        layout.addWidget(self.create_status)

        self.raw_url_label = QLabel("")
        self.raw_url_label.setWordWrap(True)
        self.raw_url_label.setStyleSheet("font-size: 11px; color: #8B8F98;")
        layout.addWidget(self.raw_url_label)
        for w in (self.gist_id_input, self.filename_input):
            w.textChanged.connect(self._update_preview_url)
        self._update_preview_url()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _create_gist(self):
        token = self.token_input.text().strip()
        filename = self.filename_input.text().strip() or "revoked_keys.json"
        if not token:
            self.create_status.setText("✗ Enter your access token first.")
            self.create_status.setStyleSheet("color: #F87171; font-size: 12px; font-weight: 700;")
            return
        self.create_status.setText("Creating gist…")
        self.create_status.setStyleSheet("color: #9CA3AF; font-size: 12px; font-weight: 700;")
        QApplication.processEvents()
        try:
            result = revocation_admin.create_gist(token, filename)
        except revocation_admin.GitHubError as e:
            self.create_status.setText(f"✗ Failed to create gist: {e}")
            self.create_status.setStyleSheet("color: #F87171; font-size: 12px; font-weight: 700;")
            return
        self.gist_id_input.setText(result.get("id", ""))
        self.create_status.setText("✓ Gist created — Gist ID filled in below.")
        self.create_status.setStyleSheet("color: #34D399; font-size: 12px; font-weight: 700;")
        self._update_preview_url()

    def _update_preview_url(self):
        cfg = self.current_config()
        url = revocation_admin.raw_url_for(cfg)
        if url:
            self.raw_url_label.setText(
                f"license_core.py's REVOCATION_URL should be set to:\n{url}"
            )
        else:
            self.raw_url_label.setText("")

    def current_config(self) -> dict:
        return {
            "gist_id": self.gist_id_input.text().strip(),
            "filename": self.filename_input.text().strip() or "revoked_keys.json",
            "token": self.token_input.text().strip(),
        }


class KeyGeneratorWindow(QMainWindow):
    """
    Offset Key Generator — internal tool for producing license keys that
    unlock Offset Auto Renamer. Keep this tool private; anyone who has it
    can mint working keys.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Offset Key Generator")
        self.resize(760, 700)
        self.setMinimumSize(620, 560)
        self.setWindowIcon(load_multi_res_icon())
        self.generated_keys = []
        self.init_ui()
        self.setStyleSheet(build_stylesheet(theme))
        cfg = revocation_admin.load_config()
        if cfg.get("gist_id") and cfg.get("token"):
            self.refresh_revoked_list()
        self.refresh_key_log()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header
        header_card = QFrame()
        header_card.setObjectName("HeaderCard")
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(18, 14, 18, 14)

        logo_label = QLabel()
        png_file = Path(__file__).parent / "illust.png"
        if png_file.exists():
            logo_label.setPixmap(
                QPixmap(str(png_file)).scaled(44, 44, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        header_layout.addWidget(logo_label)
        header_layout.addSpacing(12)

        title_vbox = QVBoxLayout()
        title = QLabel("OFFSET KEY GENERATOR")
        title.setObjectName("BrandLabel")
        sub = QLabel("Generate license keys that unlock Offset Auto Renamer")
        sub.setObjectName("SubLabel")
        title_vbox.addWidget(title)
        title_vbox.addWidget(sub)
        header_layout.addLayout(title_vbox)
        header_layout.addStretch()
        layout.addWidget(header_card)

        # Tabs: Generate | Key Log
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_generate_tab(), "⚡ Generate")
        self.tabs.addTab(self._build_key_log_tab(), "🗂 Key Log")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs, stretch=1)

    # ---------------- GENERATE TAB ----------------
    def _build_generate_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(16)

        # Generate controls
        controls_card = QFrame()
        controls_card.setObjectName("Card")
        controls_layout = QHBoxLayout(controls_card)
        controls_layout.setContentsMargins(16, 16, 16, 16)

        controls_layout.addWidget(QLabel("Type:"))
        self.type_combo = QComboBox()
        self.type_combo.addItem("Lifetime", license_core.KEY_TYPE_LIFETIME)
        self.type_combo.addItem("1 Month (30 days)", license_core.KEY_TYPE_MONTH)
        self.type_combo.setFixedWidth(170)
        controls_layout.addWidget(self.type_combo)
        controls_layout.addSpacing(16)

        controls_layout.addWidget(QLabel("Quantity:"))
        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, 500)
        self.qty_spin.setValue(1)
        self.qty_spin.setFixedWidth(80)
        controls_layout.addWidget(self.qty_spin)
        controls_layout.addStretch()

        generate_btn = QPushButton("⚡ Generate Key(s)")
        generate_btn.setObjectName("PrimaryButton")
        generate_btn.clicked.connect(self.generate_keys)
        controls_layout.addWidget(generate_btn)

        layout.addWidget(controls_card)

        # Results list
        results_card = QFrame()
        results_card.setObjectName("Card")
        results_layout = QVBoxLayout(results_card)
        results_layout.setContentsMargins(14, 14, 14, 14)

        results_header = QHBoxLayout()
        results_title = QLabel("Generated This Session")
        results_title.setObjectName("HeaderLabel")
        results_header.addWidget(results_title)
        results_header.addStretch()

        copy_all_btn = QPushButton("📋 Copy All")
        copy_all_btn.clicked.connect(self.copy_all)
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("DangerButton")
        clear_btn.clicked.connect(self.clear_keys)
        results_header.addWidget(copy_all_btn)
        results_header.addWidget(clear_btn)
        results_layout.addLayout(results_header)

        self.key_list = QListWidget()
        self.key_list.itemDoubleClicked.connect(self.copy_single)
        self.key_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.key_list.customContextMenuRequested.connect(self._key_list_context_menu)
        results_layout.addWidget(self.key_list)

        hint = QLabel(
            "💡 Double-click a key to copy it, right-click to deactivate it. Every key "
            "generated here is also saved to the Key Log tab. Keep this tool private — "
            "anyone with it can mint valid keys."
        )
        hint.setObjectName("SubLabel")
        hint.setWordWrap(True)
        results_layout.addWidget(hint)

        layout.addWidget(results_card, stretch=1)

        # Verifier
        verify_card = QFrame()
        verify_card.setObjectName("Card")
        verify_layout = QVBoxLayout(verify_card)
        verify_layout.setContentsMargins(14, 14, 14, 14)

        verify_title = QLabel("Verify a Key")
        verify_title.setObjectName("HeaderLabel")
        verify_layout.addWidget(verify_title)

        verify_row = QHBoxLayout()
        self.verify_input = QLineEdit()
        self.verify_input.setPlaceholderText("OFST-XXXX-XXXX-XXXX-XXXX")
        self.verify_input.textChanged.connect(lambda t: self.verify_input.setText(t.upper()) if t != t.upper() else None)
        verify_btn = QPushButton("Check")
        verify_btn.clicked.connect(self.verify_key)
        verify_row.addWidget(self.verify_input)
        verify_row.addWidget(verify_btn)
        verify_layout.addLayout(verify_row)

        self.verify_status = QLabel(" ")
        self.verify_status.setStyleSheet("font-size: 12px; font-weight: 700;")
        verify_layout.addWidget(self.verify_status)

        layout.addWidget(verify_card)

        return tab

    # ---------------- KEY LOG TAB ----------------
    def _build_key_log_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(12)

        info = QLabel(
            "Every key you generate here is logged locally on this machine "
            "(key, type, length, issue date). Status is checked live against "
            "your deactivation Gist. HWID/notes are filled in by you — ask the "
            "customer to send you the \"System ID\" shown on their activation "
            "screen, then paste it in here."
        )
        info.setObjectName("SubLabel")
        info.setWordWrap(True)
        layout.addWidget(info)

        toolbar = QHBoxLayout()
        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.clicked.connect(self.refresh_key_log)
        toolbar.addWidget(refresh_btn)

        settings_btn = QPushButton("⚙ Deactivation Settings")
        settings_btn.clicked.connect(self.open_settings)
        toolbar.addWidget(settings_btn)

        add_existing_btn = QPushButton("+ Add Existing Key")
        add_existing_btn.clicked.connect(self.add_existing_key_to_log)
        toolbar.addWidget(add_existing_btn)
        toolbar.addStretch()

        self.key_log_status = QLabel(" ")
        self.key_log_status.setStyleSheet("font-size: 12px; font-weight: 700;")
        toolbar.addWidget(self.key_log_status)
        layout.addLayout(toolbar)

        self.key_table = QTableWidget(0, 6)
        self.key_table.setHorizontalHeaderLabels(
            ["Key", "Type", "Length", "Issued", "Status", "HWID"]
        )
        self.key_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.key_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.key_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.key_table.verticalHeader().setVisible(False)
        header = self.key_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.key_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.key_table.customContextMenuRequested.connect(self._key_table_context_menu)
        self.key_table.itemDoubleClicked.connect(self._key_table_double_clicked)
        layout.addWidget(self.key_table, stretch=1)

        actions_row = QHBoxLayout()
        set_hwid_btn = QPushButton("🖥 Set HWID…")
        set_hwid_btn.clicked.connect(self.set_hwid_for_selected)
        deactivate_btn = QPushButton("🚫 Deactivate Selected")
        deactivate_btn.setObjectName("DangerButton")
        deactivate_btn.clicked.connect(self.deactivate_selected)
        reactivate_btn = QPushButton("♻ Reactivate Selected")
        reactivate_btn.clicked.connect(self.reactivate_selected)
        delete_btn = QPushButton("🗑 Delete From Log")
        delete_btn.setObjectName("DangerButton")
        delete_btn.clicked.connect(self.delete_selected_from_log)
        actions_row.addWidget(set_hwid_btn)
        actions_row.addWidget(deactivate_btn)
        actions_row.addWidget(reactivate_btn)
        actions_row.addStretch()
        actions_row.addWidget(delete_btn)
        layout.addLayout(actions_row)

        hint = QLabel(
            "💡 \"Delete From Log\" only removes a key from this local list — it does "
            "NOT stop the key from working. Use Deactivate for that. Double-click a "
            "key to copy it; double-click the HWID cell to edit it."
        )
        hint.setObjectName("SubLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        return tab

    def _on_tab_changed(self, index):
        if self.tabs.tabText(index).endswith("Key Log"):
            self.refresh_key_log()

    # ---------------- GENERATE ----------------
    def generate_keys(self):
        count = self.qty_spin.value()
        key_type = self.type_combo.currentData()
        for _ in range(count):
            key = license_core.generate_key(key_type)
            self.generated_keys.append(key)
            label = license_core.describe_key(key)
            item = QListWidgetItem(f"🔑  {key}   —   {label}")
            item.setData(Qt.UserRole, key)
            self.key_list.addItem(item)
            key_log.add_key(key, key_type)
        self.key_list.scrollToBottom()
        self.refresh_key_log()

    def copy_single(self, item: QListWidgetItem):
        key = item.data(Qt.UserRole)
        if key:
            QApplication.clipboard().setText(key)

    def copy_all(self):
        if not self.generated_keys:
            return
        QApplication.clipboard().setText("\n".join(self.generated_keys))
        QMessageBox.information(self, "Copied", f"Copied {len(self.generated_keys)} key(s) to clipboard.")

    def clear_keys(self):
        self.generated_keys.clear()
        self.key_list.clear()

    def verify_key(self):
        key = self.verify_input.text().strip()
        if not license_core.is_valid_key(key):
            self.verify_status.setText("✗ Invalid key")
            self.verify_status.setStyleSheet(f"color: {DANGER}; font-size: 12px; font-weight: 700;")
            return

        label = license_core.describe_key(key)

        if license_core.is_key_expired(key):
            self.verify_status.setText(f"⚠ Valid format, but this key has expired ({label})")
            self.verify_status.setStyleSheet(f"color: {DANGER}; font-size: 12px; font-weight: 700;")
            return

        cfg = revocation_admin.load_config()
        if cfg.get("gist_id") and cfg.get("token"):
            try:
                remote_keys = revocation_admin.get_remote_list(cfg)
                if key.upper() in remote_keys:
                    self.verify_status.setText(f"⚠ Valid format, but this key has been deactivated ({label})")
                    self.verify_status.setStyleSheet(f"color: {DANGER}; font-size: 12px; font-weight: 700;")
                    return
            except revocation_admin.GitHubError:
                pass  # fall through to plain "valid" result if we can't reach GitHub

        self.verify_status.setText(f"✓ Valid key ({label})")
        self.verify_status.setStyleSheet(f"color: {SUCCESS}; font-size: 12px; font-weight: 700;")

    def _key_list_context_menu(self, pos):
        item = self.key_list.itemAt(pos)
        if not item:
            return
        key = item.data(Qt.UserRole)
        menu = QMenu(self)
        copy_act = QAction("📋 Copy", self)
        copy_act.triggered.connect(lambda: QApplication.clipboard().setText(key))
        deactivate_act = QAction("🚫 Deactivate", self)
        deactivate_act.triggered.connect(lambda: self._deactivate_keys_by_string([key]))
        menu.addAction(copy_act)
        menu.addAction(deactivate_act)
        menu.exec_(self.key_list.viewport().mapToGlobal(pos))

    # ---------------- DEACTIVATION (shared settings) ----------------
    def open_settings(self):
        dlg = RevocationSettingsDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            revocation_admin.save_config(dlg.current_config())
            self.key_log_status.setText(
                "Settings saved. Make sure license_core.py's REVOCATION_URL "
                "matches the URL shown above before you rebuild the .exe."
            )
            self.key_log_status.setStyleSheet(f"color: {theme.accent_dim}; font-size: 12px; font-weight: 700;")
            self.refresh_revoked_list()
            self.refresh_key_log()

    def _require_configured(self) -> dict:
        cfg = revocation_admin.load_config()
        if not (cfg.get("gist_id") and cfg.get("token")):
            QMessageBox.information(
                self, "Deactivation not set up",
                "Set up where to host the deactivation list first (Settings button) "
                "— you'll need a GitHub personal access token with 'gist' scope, "
                "then click 'Create New Gist'."
            )
            self.open_settings()
            return None
        return cfg

    def refresh_revoked_list(self):
        """Pulls the current remote revoked-keys set (used to color Key Log status)."""
        cfg = revocation_admin.load_config()
        if not (cfg.get("gist_id") and cfg.get("token")):
            self._revoked_cache = None
            return set()
        try:
            remote_keys = revocation_admin.get_remote_list(cfg)
        except revocation_admin.GitHubError as e:
            self.key_log_status.setText(f"✗ Couldn't load deactivated list: {e}")
            self.key_log_status.setStyleSheet(f"color: {DANGER}; font-size: 12px; font-weight: 700;")
            self._revoked_cache = None
            return set()
        self._revoked_cache = remote_keys
        return remote_keys

    def _deactivate_keys_by_string(self, keys: list):
        cfg = self._require_configured()
        if not cfg:
            return
        self.key_log_status.setText("Deactivating…")
        self.key_log_status.setStyleSheet(f"color: {theme.accent_dim}; font-size: 12px; font-weight: 700;")
        QApplication.processEvents()
        failed = []
        for key in keys:
            if not license_core.is_valid_key(key):
                failed.append(key)
                continue
            try:
                revocation_admin.revoke_key(cfg, key)
            except revocation_admin.GitHubError as e:
                failed.append(f"{key} ({e})")
        if failed:
            self.key_log_status.setText(f"✗ Failed for: {', '.join(failed)}")
            self.key_log_status.setStyleSheet(f"color: {DANGER}; font-size: 12px; font-weight: 700;")
        else:
            self.key_log_status.setText(f"✓ Deactivated {len(keys)} key(s).")
            self.key_log_status.setStyleSheet(f"color: {SUCCESS}; font-size: 12px; font-weight: 700;")
        self.refresh_revoked_list()
        self.refresh_key_log()

    def _reactivate_keys_by_string(self, keys: list):
        cfg = self._require_configured()
        if not cfg:
            return
        failed = []
        for key in keys:
            try:
                revocation_admin.unrevoke_key(cfg, key)
            except revocation_admin.GitHubError as e:
                failed.append(f"{key} ({e})")
        if failed:
            self.key_log_status.setText(f"✗ Failed for: {', '.join(failed)}")
            self.key_log_status.setStyleSheet(f"color: {DANGER}; font-size: 12px; font-weight: 700;")
        else:
            self.key_log_status.setText(f"✓ Reactivated {len(keys)} key(s).")
            self.key_log_status.setStyleSheet(f"color: {SUCCESS}; font-size: 12px; font-weight: 700;")
        self.refresh_revoked_list()
        self.refresh_key_log()

    # ---------------- KEY LOG ----------------
    def refresh_key_log(self):
        revoked = self.refresh_revoked_list()
        cfg = revocation_admin.load_config()
        configured = bool(cfg.get("gist_id") and cfg.get("token"))
        records = key_log.load_log()
        records.sort(key=lambda r: r.get("generated_at", ""), reverse=True)

        self.key_table.setRowCount(0)
        for rec in records:
            row = self.key_table.rowCount()
            self.key_table.insertRow(row)

            key_item = QTableWidgetItem(rec.get("key", ""))
            key_item.setData(Qt.UserRole, rec.get("key", ""))
            self.key_table.setItem(row, 0, key_item)

            type_label = "Lifetime" if rec.get("type") == license_core.KEY_TYPE_LIFETIME else "1 Month"
            self.key_table.setItem(row, 1, QTableWidgetItem(type_label))

            self.key_table.setItem(row, 2, QTableWidgetItem(str(rec.get("length", len(rec.get("key", ""))))))
            self.key_table.setItem(row, 3, QTableWidgetItem(rec.get("issued", "")))

            if not configured:
                status_text, status_color = "Unknown (not set up)", "#8B8F98"
            elif revoked is not None and rec.get("key", "").upper() in revoked:
                status_text, status_color = "🚫 Deactivated", DANGER
            elif revoked is not None:
                status_text, status_color = "✓ Active", SUCCESS
            else:
                status_text, status_color = "Unknown (offline?)", "#8B8F98"
            status_item = QTableWidgetItem(status_text)
            status_item.setForeground(_qcolor(status_color))
            self.key_table.setItem(row, 4, status_item)

            hwid_item = QTableWidgetItem(rec.get("hwid", "") or "—")
            self.key_table.setItem(row, 5, hwid_item)

        count_txt = f"{len(records)} key(s) logged locally."
        if configured and revoked is not None:
            count_txt += f" {len(revoked)} currently deactivated."
        self.key_log_status.setText(count_txt)
        self.key_log_status.setStyleSheet(f"color: {theme.accent_dim}; font-size: 12px; font-weight: 700;")

    def _selected_keys(self) -> list:
        rows = sorted({idx.row() for idx in self.key_table.selectedIndexes()})
        keys = []
        for row in rows:
            item = self.key_table.item(row, 0)
            if item:
                keys.append(item.data(Qt.UserRole) or item.text())
        return keys

    def _key_table_double_clicked(self, item: QTableWidgetItem):
        row = item.row()
        key_item = self.key_table.item(row, 0)
        key = key_item.data(Qt.UserRole) if key_item else None
        if item.column() == 5:  # HWID column
            self.set_hwid_for_selected()
        elif key:
            QApplication.clipboard().setText(key)
            self.key_log_status.setText(f"📋 Copied {key} to clipboard.")
            self.key_log_status.setStyleSheet(f"color: {theme.accent_dim}; font-size: 12px; font-weight: 700;")

    def set_hwid_for_selected(self):
        keys = self._selected_keys()
        if len(keys) != 1:
            QMessageBox.information(self, "Select one key", "Select exactly one key to set its HWID.")
            return
        key = keys[0]
        records = key_log.load_log()
        rec = key_log.find(records, key)
        current = rec.get("hwid", "") if rec else ""
        text, ok = QInputDialog.getText(
            self, "Set HWID",
            f"HWID / System ID for {key}\n(ask the customer for the \"System ID\" "
            "shown on their activation screen):",
            text=current,
        )
        if ok:
            key_log.set_hwid(key, text)
            self.refresh_key_log()

    def deactivate_selected(self):
        keys = self._selected_keys()
        if not keys:
            QMessageBox.information(self, "No selection", "Select one or more keys first.")
            return
        self._deactivate_keys_by_string(keys)

    def reactivate_selected(self):
        keys = self._selected_keys()
        if not keys:
            QMessageBox.information(self, "No selection", "Select one or more keys first.")
            return
        self._reactivate_keys_by_string(keys)

    def delete_selected_from_log(self):
        keys = self._selected_keys()
        if not keys:
            QMessageBox.information(self, "No selection", "Select one or more keys first.")
            return
        reply = QMessageBox.question(
            self, "Delete from log",
            f"Remove {len(keys)} key(s) from your local Key Log?\n\n"
            "This only deletes your local notes about them — it does NOT "
            "deactivate the key(s). Use Deactivate if you want to stop them "
            "from working.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for key in keys:
            key_log.remove_key(key)
        self.refresh_key_log()

    def add_existing_key_to_log(self):
        text, ok = QInputDialog.getText(
            self, "Add Existing Key",
            "Paste a previously-generated key to add it to the log\n"
            "(type and issue date are read from the key itself):",
        )
        if not ok or not text.strip():
            return
        key = text.strip().upper()
        if not license_core.is_valid_key(key):
            QMessageBox.warning(self, "Invalid key", "That doesn't look like a valid key.")
            return
        key_log.add_key(key)
        self.refresh_key_log()

    def _key_table_context_menu(self, pos):
        item = self.key_table.itemAt(pos)
        if not item:
            return
        keys = self._selected_keys()
        if not keys:
            return
        menu = QMenu(self)
        copy_act = QAction("📋 Copy Key" if len(keys) == 1 else "📋 Copy Keys", self)
        copy_act.triggered.connect(lambda: QApplication.clipboard().setText("\n".join(keys)))
        hwid_act = QAction("🖥 Set HWID…", self)
        hwid_act.setEnabled(len(keys) == 1)
        hwid_act.triggered.connect(self.set_hwid_for_selected)
        deactivate_act = QAction("🚫 Deactivate", self)
        deactivate_act.triggered.connect(lambda: self._deactivate_keys_by_string(keys))
        reactivate_act = QAction("♻ Reactivate", self)
        reactivate_act.triggered.connect(lambda: self._reactivate_keys_by_string(keys))
        delete_act = QAction("🗑 Delete From Log", self)
        delete_act.triggered.connect(self.delete_selected_from_log)
        menu.addAction(copy_act)
        menu.addAction(hwid_act)
        menu.addSeparator()
        menu.addAction(deactivate_act)
        menu.addAction(reactivate_act)
        menu.addSeparator()
        menu.addAction(delete_act)
        menu.exec_(self.key_table.viewport().mapToGlobal(pos))


def _qcolor(hex_str: str):
    from PyQt5.QtGui import QColor
    return QColor(hex_str)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(build_stylesheet(theme))
    app.setWindowIcon(load_multi_res_icon())
    window = KeyGeneratorWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
