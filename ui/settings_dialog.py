'''Settings: framerate, hotkey bindings, and the entry point to calibration.'''
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QGroupBox, QSpinBox, QLabel,
                               QPushButton, QHBoxLayout, QDialogButtonBox)

from core.hotkeys import ACTIONS, DEFAULTS, roblox_conflict
from .app import PixelerApp
from .floating_panel import STYLE
from .widgets import KeyCapture


class SettingsDialog(QDialog):
    calibrate_requested = Signal()

    def __init__(self, app: PixelerApp, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle("Pixeler — Settings")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(380)
        root = QVBoxLayout(self)

        # ---- calibration
        cal = QGroupBox("Calibration")
        cl = QVBoxLayout(cal)
        self.cal_status = QLabel()
        cl.addWidget(self.cal_status)
        fps_row = QFormLayout()
        self.fps = QSpinBox(minimum=1, maximum=1000)
        self.fps.setValue(app.calibration.fps or 60)
        self.fps.setToolTip("Your average Roblox FPS (Shift+F5 in Roblox shows it). Inputs are spaced to ~1.2 frames.")
        fps_row.addRow("Roblox FPS", self.fps)
        cl.addLayout(fps_row)
        self.cal_button = QPushButton("Calibrate canvas and color picker…")
        self.cal_button.clicked.connect(self._calibrate)
        cl.addWidget(self.cal_button)
        root.addWidget(cal)

        # ---- hotkeys
        hk = QGroupBox("Hotkeys (global — work while the game has focus)")
        hl = QFormLayout(hk)
        self.captures = {}
        for action, label, _ in ACTIONS:
            cap = KeyCapture(app.hotkeys.key_for(action))
            cap.keySequenceChanged.connect(self._check_conflicts)
            self.captures[action] = cap
            hl.addRow(label, cap)
        restore = QPushButton("Restore defaults")
        restore.clicked.connect(self._restore_defaults)
        hl.addRow("", restore)
        self.hk_note = QLabel()
        self.hk_note.setWordWrap(True)
        hl.addRow(self.hk_note)
        self._check_conflicts()
        root.addWidget(hk)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.refresh_status()

    def refresh_status(self):
        ok = self.app.calibration.is_config_valid()
        self.cal_status.setText("● Calibration OK" if ok else "● Not calibrated — drawing is disabled")
        self.cal_status.setStyleSheet(f"color: {'#6bd47f' if ok else '#ff6b6b'}; font-weight: bold;")
        self.fps.setValue(self.app.calibration.fps or self.fps.value())

    def _calibrate(self):
        self._apply_fps()
        self.calibrate_requested.emit()

    def _check_conflicts(self, *_):
        if len(self.captures) < len(ACTIONS):
            return
        bad = []
        for action, label, _ in ACTIONS:
            what = roblox_conflict(self.captures[action].key())
            if what:
                bad.append(f"{label}: Roblox uses that key for {what}")
        if bad:
            self.hk_note.setText("⚠ " + "; ".join(bad) + ". The game reacts to it even with Ctrl/Shift held.")
            self.hk_note.setStyleSheet("color: #ffb347; font-size: 11px;")
        else:
            self.hk_note.setText("Use modifier combos (Ctrl+Shift+…) so keys never type into chat. "
                                 "Avoid Space, W/A/S/D, I/O, Esc, Tab — Roblox acts on those regardless of modifiers.")
            self.hk_note.setStyleSheet("color: #a0a3a8; font-size: 11px;")

    def _restore_defaults(self):
        for action, cap in self.captures.items():
            cap.set_key(DEFAULTS[action])

    def _apply_fps(self):
        self.app.calibration.fps = self.fps.value()
        if self.app.calibration.is_config_valid():
            self.app.calibration.save_config()

    def accept(self):
        self._apply_fps()
        failed = []
        for action, cap in self.captures.items():
            key = cap.key()
            if key != self.app.hotkeys.key_for(action):
                if not self.app.hotkeys.rebind(action, key):
                    failed.append(action)
        self.app.save_hotkeys()
        if failed:
            self.hk_note.setText("Some combinations were rejected and are now unbound: " +
                                 ", ".join(failed) + ". Pick another key.")
            self.hk_note.setStyleSheet("color: #ff6b6b; font-size: 11px;")
            return
        super().accept()
