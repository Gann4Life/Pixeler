'''Input panel: source image with crop editor, transport, load buttons, timeline.'''
from PySide6.QtCore import Qt
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QSlider, QLabel

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

        self.body.setContentsMargins(4, 4, 4, 4)
        self.body.setSpacing(2)

        # ---- image + crop (fills the panel)
        self.editor = CropEditor()
        self.editor.set_crop(app.crop)
        self.editor.crop_changed.connect(app.set_crop)
        self.body.addWidget(self.editor, 1)

        # ---- timeline, directly under the image
        tl = QHBoxLayout()
        tl.setSpacing(6)
        tl.setContentsMargins(2, 0, 2, 0)
        self.timeline = QSlider(Qt.Horizontal, minimum=0, maximum=0)
        self.timeline.setToolTip("Timeline — drag to scrub; Play resumes from here.\n"
                                 "Crop/adjustment edits while paused rebuild the plan and clamp this position.")
        self.timeline.sliderPressed.connect(self._on_scrub_start)
        self.timeline.sliderReleased.connect(lambda: app.scrubbing.emit(False))
        self.timeline.valueChanged.connect(self._on_timeline_value)
        self.timeline_label = QLabel("0 / 0")
        self.timeline_label.setStyleSheet("font-size: 11px; color: #a0a3a8;")
        self.timeline_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        tl.addWidget(self.timeline, 1)
        tl.addWidget(self.timeline_label)
        self.body.addLayout(tl)

        # ---- compact button row: transport/load on the left, zoom on the right
        row = QHBoxLayout()
        row.setSpacing(2)
        row.setContentsMargins(0, 0, 0, 0)

        def tool(text, slot, font_px=14):
            b = QToolButton(text=text)
            b.setFixedSize(QSize(30, 24))
            b.setStyleSheet(f'QToolButton {{ font-family: "Segoe UI Symbol", "Segoe UI Emoji"; font-size: {font_px}px; '
                            f'background: #35383d; border: 1px solid #45484e; border-radius: 3px; padding: 0; }}'
                            f'QToolButton:hover {{ background: #45484e; }} QToolButton:disabled {{ color: #6d7075; }}')
            b.clicked.connect(slot)
            row.addWidget(b)
            return b

        self.play_button = tool("▶", app.play_pause)
        self.stop_button = tool("⏹", app.stop)
        self.stop_button.setEnabled(False)
        row.addSpacing(6)
        self.file_button = tool("📁", lambda: app.load_file())
        self.clip_button = tool("📋", app.load_clipboard)
        row.addSpacing(6)
        self.reset_crop_button = tool("⟲", app.reset_crop)
        row.addStretch(1)
        self.zoom_out_button = tool("−", self.editor.zoom_out, 16)
        self.zoom_in_button = tool("+", self.editor.zoom_in, 16)
        self.fit_button = tool("⊡", self.editor.reset_view, 16)
        self.body.addLayout(row)


        # ---- wiring
        self._syncing = False
        app.source_changed.connect(self.editor.set_image)
        app.crop_changed.connect(self.editor.set_crop)
        app.output_changed.connect(self._on_output)
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
        self.zoom_out_button.setToolTip("Zoom out  (mouse wheel)")
        self.zoom_in_button.setToolTip("Zoom in  (mouse wheel)")
        self.fit_button.setToolTip("Fit image  (middle double-click or 0)")
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
        self.app.scrubbing.emit(True)

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
