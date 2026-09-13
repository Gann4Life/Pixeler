'''Input panel: source image with crop editor, transport, load buttons, timeline.'''
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSlider, QLabel, QSizePolicy

from core.drawer import IDLE, RUNNING, PAUSED
from .app import PixelerApp
from .crop_editor import CropEditor
from .floating_panel import FloatingPanel


class InputPanel(FloatingPanel):
    def __init__(self, app: PixelerApp):
        super().__init__("input", "Input", app.state)
        self.app = app
        self.settings_button = self.add_title_button("⚙", "Settings and calibration", self._open_settings)
        self.open_settings = None   # injected by __main__

        # ---- image + crop
        self.editor = CropEditor()
        self.editor.set_crop(app.crop)
        self.editor.crop_changed.connect(app.set_crop)
        self.body.addWidget(self.editor, 1)

        # ---- transport / load row
        row = QHBoxLayout()
        row.setSpacing(4)
        self.play_button = QPushButton("▶")
        self.play_button.clicked.connect(app.play_pause)
        self.stop_button = QPushButton("⏹")
        self.stop_button.clicked.connect(app.stop)
        self.stop_button.setEnabled(False)
        self.file_button = QPushButton("📁")
        self.file_button.clicked.connect(lambda: app.load_file())
        self.clip_button = QPushButton("📋")
        self.clip_button.clicked.connect(app.load_clipboard)
        self.reset_crop_button = QPushButton("⟲ crop")
        self.reset_crop_button.clicked.connect(app.reset_crop)
        for b in (self.play_button, self.stop_button, self.file_button, self.clip_button, self.reset_crop_button):
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.setMinimumWidth(28)
            b.setStyleSheet('font-family: "Segoe UI Symbol", "Segoe UI Emoji"; font-size: 15px; padding: 2px 6px;')
        row.addWidget(self.play_button)
        row.addWidget(self.stop_button)
        row.addSpacing(8)
        row.addWidget(self.file_button)
        row.addWidget(self.clip_button)
        row.addSpacing(8)
        row.addWidget(self.reset_crop_button)
        self.body.addLayout(row)

        # ---- timeline
        tl = QHBoxLayout()
        tl.setSpacing(6)
        self.timeline = QSlider(Qt.Horizontal, minimum=0, maximum=0)
        self.timeline.setToolTip("Timeline — drag to scrub; Play resumes from here.\n"
                                 "Crop/adjustment edits while paused rebuild the plan and clamp this position.")
        self.timeline.sliderPressed.connect(self._on_scrub_start)
        self.timeline.valueChanged.connect(self._on_timeline_value)
        self.timeline_label = QLabel("0 / 0")
        self.timeline_label.setMinimumWidth(70)
        self.timeline_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        tl.addWidget(self.timeline, 1)
        tl.addWidget(self.timeline_label)
        self.body.addLayout(tl)

        # ---- status line
        self.status_label = QLabel("Load an image to begin.")
        self.status_label.setStyleSheet("color: #a0a3a8; font-size: 11px;")
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.body.addWidget(self.status_label)

        # ---- wiring
        self._syncing = False
        app.source_changed.connect(self.editor.set_image)
        app.crop_changed.connect(self.editor.set_crop)
        app.output_changed.connect(self._on_output)
        app.status.connect(self._on_status)
        app.drawer.progress.connect(self._on_progress)
        app.drawer.state_changed.connect(self._on_state)
        self.refresh_tooltips()

    # ---- tooltips reflect the live hotkeys ------------------------------------------------
    def refresh_tooltips(self):
        hk = self.app.hotkeys
        self.play_button.setToolTip(hk.tooltip("play_pause"))
        self.stop_button.setToolTip(hk.tooltip("stop"))
        self.file_button.setToolTip(hk.tooltip("load_file"))
        self.clip_button.setToolTip(hk.tooltip("load_clipboard"))
        self.reset_crop_button.setToolTip(hk.tooltip("reset_crop", "Reset crop to the whole image"))
        from core.hotkeys import pretty
        self.hide_action.setText(f"Hide this panel  (show again: {pretty(hk.key_for('toggle_panels'))})")
        self.editor.setToolTip("Drag handles to crop. Shift = keep aspect ratio, Alt = symmetric.\n"
                               "Drag inside to move, drag on the empty area for a new crop.\n"
                               "Wheel = zoom, middle/right-drag = pan, middle double-click or 0 = fit.")

    # ---- slots ----------------------------------------------------------------------------------
    def _open_settings(self):
        if self.open_settings:
            self.open_settings()

    def _on_output(self, img, steps):
        self._syncing = True
        self.timeline.setMaximum(len(steps))
        self.timeline.setValue(min(self.app.drawer.next_index, len(steps)))
        self._syncing = False
        self._update_timeline_label()

    def _on_progress(self, index: int):
        self._syncing = True
        self.timeline.setValue(index)
        self._syncing = False
        self._update_timeline_label()

    def _on_scrub_start(self):
        if self.app.drawer.state == RUNNING:
            self.app.drawer.pause()

    def _on_timeline_value(self, value: int):
        if self._syncing:
            return
        self.app.seek(value)
        self._update_timeline_label()

    def _update_timeline_label(self):
        v, n = self.timeline.value(), self.timeline.maximum()
        self.timeline_label.setText(f"{v} / {n}")
        steps = self.app.steps
        if steps and v < len(steps):
            s = steps[v]
            self.timeline_label.setToolTip(f"Next: {s.color} at ({s.gx}, {s.gy})")
        else:
            self.timeline_label.setToolTip("")

    def _on_state(self, state: str):
        running = state == RUNNING
        self.play_button.setText("⏸" if running else "▶")
        self.stop_button.setEnabled(state != IDLE)
        for w in (self.file_button, self.clip_button, self.reset_crop_button, self.settings_button):
            w.setEnabled(not running)
        self.editor.set_editable(not running)

    def _on_status(self, message: str, is_error: bool):
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {'#ff6b6b' if is_error else '#a0a3a8'}; font-size: 11px;")
