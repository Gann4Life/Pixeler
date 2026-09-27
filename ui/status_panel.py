'''Status panel: two lines in a corner — what is happening, and a hint
(hotkeys / tips) that fits the current situation.'''
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from core.drawer import IDLE, RUNNING, PAUSED
from core.hotkeys import pretty
from .app import PixelerApp
from .floating_panel import FloatingPanel


class StatusPanel(FloatingPanel):
    def __init__(self, app: PixelerApp):
        super().__init__("status", "Status", app.state, min_size=(220, 90))
        self.app = app
        self.body.setContentsMargins(8, 4, 8, 6)
        self.body.setSpacing(2)

        self.line1 = QLabel("Ready.")
        self.line1.setStyleSheet("font-size: 12px; color: #e3e5e8;")
        self.line1.setWordWrap(True)
        self.line1.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.line2 = QLabel()
        self.line2.setStyleSheet("font-size: 11px; color: #a0a3a8;")
        self.line2.setWordWrap(True)
        self.body.addWidget(self.line1)
        self.body.addWidget(self.line2)
        self.body.addStretch(1)

        self._drawer_state = IDLE
        self._index = 0
        self._last_message = ""

        app.status.connect(self._on_status)
        app.source_changed.connect(lambda _: self.refresh_hint())
        app.output_changed.connect(lambda *_: self.refresh_hint())
        app.drawer.state_changed.connect(self._on_state)
        app.drawer.progress.connect(self._on_progress)
        app.drawer.message.connect(self._on_message)
        self.refresh_hint()

    # ---- line 1: what is happening -----------------------------------------------------
    def _on_status(self, message: str, is_error: bool):
        self._last_message = message
        self.line1.setText(message)
        self.line1.setStyleSheet(f"font-size: 12px; color: {'#ff6b6b' if is_error else '#e3e5e8'};")
        self.refresh_hint()

    def _on_message(self, message: str):
        self._last_message = message
        self._update_running_line()

    def _on_progress(self, index: int):
        self._index = index
        if self._drawer_state == RUNNING:
            self._update_running_line()

    def _update_running_line(self):
        steps = self.app.steps
        n = len(steps)
        text = self._last_message
        if self._drawer_state != IDLE and n:
            color = steps[self._index].color if self._index < n else ""
            text = f"{self._last_message}  {self._index} / {n}" + (f"  {color}" if color and self._drawer_state == RUNNING else "")
        self.line1.setText(text)
        self.line1.setStyleSheet("font-size: 12px; color: #e3e5e8;")

    def _on_state(self, state: str):
        self._drawer_state = state
        if state == PAUSED:
            self._last_message = "Paused."
            self._update_running_line()
        self.refresh_hint()

    # ---- line 2: hint for the current situation -------------------------------------------
    def refresh_hint(self):
        hk = self.app.hotkeys
        k = lambda action: pretty(hk.key_for(action))  # noqa: E731
        if self._drawer_state == RUNNING:
            hint = f"Pause {k('play_pause')}  ·  Stop {k('stop')}  ·  Hide panels {k('toggle_panels')}"
        elif self._drawer_state == PAUSED:
            hint = f"Resume {k('play_pause')}  ·  Stop {k('stop')}  ·  Drag the timeline to resume from another step"
        elif self.app.source is None:
            hint = f"Load an image: {k('load_file')} (file)  ·  {k('load_clipboard')} (clipboard)"
        elif not self.app.calibration.is_config_valid():
            hint = "Not calibrated — open ⚙ on the Input panel and drag a square over the game's canvas"
        else:
            hint = f"Play {k('play_pause')}  ·  Reset crop {k('reset_crop')}  ·  Shift = aspect, Alt = symmetric, wheel = zoom"
        self.line2.setText(hint)
