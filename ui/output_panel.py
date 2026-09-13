'''Output panel: processed 32x32 preview, adjustment properties, final/timeline toggle, stats.'''
from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import (QWidget, QBoxLayout, QFormLayout, QLabel, QSlider, QCheckBox,
                               QComboBox, QPushButton, QHBoxLayout, QSizePolicy, QScrollArea)

from core.drawer import RUNNING
from core.pipeline import Adjustments
from core.plan import render_progress, color_boundaries, estimate_seconds
from .app import PixelerApp
from .crop_editor import pil_to_qpixmap
from .floating_panel import FloatingPanel

PALETTE_CHOICES = [0, 2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, 256]


class PreviewWidget(QWidget):
    '''Nearest-neighbour, square, checkerboard behind transparent pixels.'''

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(96, 96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._pixmap = None
        self.show_grid = False

    def set_image(self, pil_image):
        self._pixmap = pil_to_qpixmap(pil_image) if pil_image is not None else None
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(23, 24, 26))
        side = min(self.width(), self.height())
        ox, oy = (self.width() - side) / 2, (self.height() - side) / 2
        target = QRectF(ox, oy, side, side)
        # checkerboard
        cell = max(4, side / 16)
        for i in range(16):
            for j in range(16):
                p.fillRect(QRectF(ox + i * cell, oy + j * cell, cell, cell),
                           QColor(60, 62, 66) if (i + j) % 2 else QColor(44, 46, 50))
        if not self._pixmap:
            p.setPen(QColor(120, 123, 128))
            p.drawText(target, Qt.AlignCenter, "No output")
            return
        p.setRenderHint(QPainter.SmoothPixmapTransform, False)
        p.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))
        if self.show_grid and side >= 128:
            n = self._pixmap.width()
            pen = QPen(QColor(0, 0, 0, 70))
            pen.setCosmetic(True)
            p.setPen(pen)
            for k in range(1, n):
                x = ox + side * k / n
                y = oy + side * k / n
                p.drawLine(QRectF(x, oy, 0, side).topLeft(), QRectF(x, oy, 0, side).bottomLeft())
                p.drawLine(QRectF(ox, y, side, 0).topLeft(), QRectF(ox, y, side, 0).topRight())


class OutputPanel(FloatingPanel):
    def __init__(self, app: PixelerApp):
        super().__init__("output", "Output", app.state)
        self.app = app
        self._syncing = False
        self._index = 0

        self.preview = PreviewWidget()
        self.preview.setToolTip("Processed result (what will be drawn)")

        # ---- properties form
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(4)
        form.setLabelAlignment(Qt.AlignRight)

        self.palette = QComboBox()
        for n in PALETTE_CHOICES:
            self.palette.addItem("Unlimited" if n == 0 else str(n), n)
        self.palette.setToolTip("Maximum number of colors. Fewer colors = fewer color picker trips = faster drawing.")
        form.addRow("Palette limit", self.palette)

        self.dither = QCheckBox()
        self.dither.setToolTip("Floyd–Steinberg dithering when the palette is limited")
        form.addRow("Dither", self.dither)

        self.sliders = {}
        for key, label, tip in (
            ("brightness", "Brightness", "1.00 = unchanged"),
            ("contrast", "Contrast", "1.00 = unchanged"),
            ("saturation", "Saturation", "0 = grayscale, 1.00 = unchanged"),
            ("gamma", "Gamma", "1.00 = unchanged; >1 brightens midtones"),
        ):
            s = QSlider(Qt.Horizontal, minimum=0, maximum=300)
            s.setToolTip(tip)
            row = QHBoxLayout()
            row.setSpacing(4)
            val = QLabel("1.00")
            val.setMinimumWidth(34)
            row.addWidget(s, 1)
            row.addWidget(val)
            form.addRow(label, row)
            self.sliders[key] = (s, val)

        self.alpha = QSlider(Qt.Horizontal, minimum=0, maximum=255)
        self.alpha.setToolTip("Pixels with alpha below this are skipped (0 = draw everything)")
        arow = QHBoxLayout()
        arow.setSpacing(4)
        self.alpha_label = QLabel("1")
        self.alpha_label.setMinimumWidth(34)
        arow.addWidget(self.alpha, 1)
        arow.addWidget(self.alpha_label)
        form.addRow("Alpha cutoff", arow)

        self.reset_button = QPushButton("Reset adjustments")
        form.addRow("", self.reset_button)

        self.final_toggle = QCheckBox("Show final result")
        self.final_toggle.setToolTip("On: preview the finished image.\n"
                                     "Off: preview only the pixels placed so far (follows the timeline).")
        form.addRow("", self.final_toggle)

        self.grid_toggle = QCheckBox("Show pixel grid")
        form.addRow("", self.grid_toggle)

        scroll = QScrollArea()
        scroll.setWidget(form_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(200)
        self.form_container = scroll

        self.split = QBoxLayout(QBoxLayout.LeftToRight)
        self.split.setSpacing(8)
        self.split.addWidget(self.preview, 3)
        self.split.addWidget(self.form_container, 2)
        self.body.addLayout(self.split, 1)

        self.stats = QLabel("—")
        self.stats.setStyleSheet("color: #a0a3a8; font-size: 11px;")
        self.body.addWidget(self.stats)

        # ---- wiring
        self._load_adjustments(app.adjustments)
        self.final_toggle.setChecked(app.state.output_shows_final)
        self.palette.currentIndexChanged.connect(self._push)
        self.dither.toggled.connect(self._push)
        for s, _ in self.sliders.values():
            s.valueChanged.connect(self._push)
        self.alpha.valueChanged.connect(self._push)
        self.reset_button.clicked.connect(lambda: app.set_adjustments(Adjustments()))
        self.final_toggle.toggled.connect(self._on_final_toggled)
        self.grid_toggle.toggled.connect(self._on_grid_toggled)

        app.output_changed.connect(self._on_output)
        app.adjustments_changed.connect(self._load_adjustments)
        app.drawer.progress.connect(self._on_progress)
        app.drawer.state_changed.connect(self._on_state)
        self._render_timer = QTimer(self, singleShot=True, interval=16)
        self._render_timer.timeout.connect(self._render)

    # ---- adjustments <-> widgets ----------------------------------------------------------
    def _load_adjustments(self, adj: Adjustments):
        self._syncing = True
        idx = self.palette.findData(adj.palette_limit)
        self.palette.setCurrentIndex(idx if idx >= 0 else 0)
        self.dither.setChecked(adj.dither)
        for key, (s, val) in self.sliders.items():
            v = float(getattr(adj, key))
            s.setValue(int(round(v * 100)))
            val.setText(f"{v:.2f}")
        self.alpha.setValue(int(adj.alpha_threshold))
        self.alpha_label.setText(str(int(adj.alpha_threshold)))
        self._syncing = False

    def _push(self, *_):
        if self._syncing:
            return
        adj = Adjustments(
            brightness=self.sliders["brightness"][0].value() / 100,
            contrast=self.sliders["contrast"][0].value() / 100,
            saturation=self.sliders["saturation"][0].value() / 100,
            gamma=max(0.05, self.sliders["gamma"][0].value() / 100),
            palette_limit=int(self.palette.currentData()),
            dither=self.dither.isChecked(),
            alpha_threshold=self.alpha.value(),
        )
        for key, (s, val) in self.sliders.items():
            val.setText(f"{s.value() / 100:.2f}")
        self.alpha_label.setText(str(self.alpha.value()))
        self.app.set_adjustments(adj)

    # ---- preview ----------------------------------------------------------------------------------
    def _on_output(self, img, steps):
        self._index = min(self._index, len(steps))
        self._render_timer.start()
        if img is None:
            self.stats.setText("—")
            return
        n_colors = len(color_boundaries(steps))
        eta = estimate_seconds(steps, self.app.calibration.get_frame_sleep_time())
        m, s = divmod(int(eta), 60)
        self.stats.setText(f"{n_colors} colors · {len(steps)} steps · ~{m}m {s:02d}s")

    def _on_progress(self, index: int):
        self._index = index
        if not self.final_toggle.isChecked():
            self._render_timer.start()

    def _render(self):
        img = self.app.output
        if img is not None and not self.final_toggle.isChecked():
            img = render_progress(img, self.app.steps, self._index)
        self.preview.set_image(img)

    def _on_final_toggled(self, checked: bool):
        self.app.state.output_shows_final = checked
        self.app.state.save()
        self._render()

    def _on_grid_toggled(self, checked: bool):
        self.preview.show_grid = checked
        self.preview.update()

    def _on_state(self, state: str):
        self.form_container.setEnabled(state != RUNNING)

    # ---- responsive: stack the form under the preview when narrow ----------------------------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        narrow = self.width() < 430
        want = QBoxLayout.TopToBottom if narrow else QBoxLayout.LeftToRight
        if self.split.direction() != want:
            self.split.setDirection(want)
