'''Output panel: processed 32x32 preview on top, a draggable/foldable divider,
adjustment properties below, and a stats line.'''
from PySide6.QtCore import Qt, QRectF, QTimer, QPoint
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import (QWidget, QFormLayout, QLabel, QSlider, QCheckBox, QComboBox,
                               QPushButton, QToolButton, QHBoxLayout, QSizePolicy, QScrollArea,
                               QSplitter, QSplitterHandle)

from core.drawer import RUNNING
from core.order import METHODS, COLOR_ORDERS, is_random
from core.pipeline import Adjustments
from core.state import SPEED_MIN, SPEED_MAX
from core.plan import render_progress, color_boundaries, estimate_seconds
from .app import PixelerApp
from .crop_editor import pil_to_qpixmap
from .floating_panel import FloatingPanel

PALETTE_CHOICES = [0, 2, 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, 256]
HANDLE_H = 10


class PreviewWidget(QWidget):
    '''Nearest-neighbour, square, checkerboard behind transparent pixels.'''

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(64, 64)
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


class FoldHandle(QSplitterHandle):
    '''Splitter handle: drag to resize the image/properties split, click to fold/unfold.'''

    def __init__(self, orientation, splitter):
        super().__init__(orientation, splitter)
        self._press = None
        self.setToolTip("Drag to resize the preview. Click to fold / unfold the properties.")

    def mousePressEvent(self, e):
        self._press = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)
        if self._press is not None and (e.position().toPoint() - self._press).manhattanLength() < 4:
            self.splitter().toggle_fold()
        self._press = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(43, 45, 49))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(110, 113, 120))
        cx, cy = self.width() / 2, self.height() / 2
        if self.splitter().folded:      # small "▲" hint when folded
            pts = [QPoint(int(cx - 5), int(cy + 2)), QPoint(int(cx + 5), int(cy + 2)), QPoint(int(cx), int(cy - 3))]
            p.drawPolygon(pts)
        else:                            # grip
            p.drawRoundedRect(QRectF(cx - 16, cy - 1.5, 32, 3), 1.5, 1.5)


class FoldSplitter(QSplitter):
    def __init__(self, parent=None):
        super().__init__(Qt.Vertical, parent)
        self.folded = False
        self._unfolded_sizes = None
        self.setHandleWidth(HANDLE_H)
        self.setChildrenCollapsible(True)

    def createHandle(self):
        return FoldHandle(self.orientation(), self)

    def toggle_fold(self):
        if self.folded:
            self.folded = False
            self.setSizes(self._unfolded_sizes or [1, 2])
        else:
            self._unfolded_sizes = self.sizes()
            self.folded = True
            self.setSizes([sum(self.sizes()), 0])
        self.handle(1).update()


class OutputPanel(FloatingPanel):
    def __init__(self, app: PixelerApp):
        super().__init__("output", "Output", app.state)
        self.app = app
        self._syncing = False
        self._index = 0
        self._scrubbing = False
        self._running = False

        self.preview = PreviewWidget()
        self.preview.setToolTip("Processed result (what will be drawn)")

        # ---- properties form
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setContentsMargins(0, 4, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(4)
        form.setLabelAlignment(Qt.AlignRight)

        self.palette = QComboBox()
        for n in PALETTE_CHOICES:
            self.palette.addItem("Unlimited" if n == 0 else str(n), n)
        self.palette.setToolTip("Maximum number of colors. Fewer colors = fewer color picker trips = faster drawing.")
        form.addRow("Palette limit", self.palette)

        self.dither = QCheckBox()
        self.dither.setToolTip("Floyd–Steinberg dithering: mixes the limited palette to fake in-between shades.\n"
                               "Only does something when the palette is limited.")
        form.addRow("Dither", self.dither)

        self.invert = QCheckBox()
        self.invert.setToolTip("Negative of the picture (applied after brightness/contrast/gamma, before the palette)")
        form.addRow("Invert colors", self.invert)

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

        # ---- draw order (how the pixels of each color are sequenced)
        self.method = QComboBox()
        for key, label, desc in METHODS:
            self.method.addItem(label, key)
            self.method.setItemData(self.method.count() - 1, desc, Qt.ToolTipRole)
        self.reroll_button = QToolButton()
        self.reroll_button.setText("🎲")
        self.reroll_button.setFixedSize(30, 24)
        self.reroll_button.setStyleSheet('font-family: "Segoe UI Symbol", "Segoe UI Emoji"; font-size: 14px;')
        self.reroll_button.setToolTip("New random seed for the Maze / Scatter / Random orders")
        mrow = QHBoxLayout()
        mrow.setSpacing(4)
        mrow.addWidget(self.method, 1)
        mrow.addWidget(self.reroll_button)
        form.addRow("Draw order", mrow)

        # ---- color order (in which order the colors are picked)
        self.color_order = QComboBox()
        for key, label, desc in COLOR_ORDERS:
            self.color_order.addItem(label, key)
            self.color_order.setItemData(self.color_order.count() - 1, desc, Qt.ToolTipRole)
        form.addRow("Color order", self.color_order)

        # ---- speed: multiplier on the per-frame wait; can be changed while drawing
        self.speed = QSlider(Qt.Horizontal, minimum=int(SPEED_MIN * 100), maximum=int(SPEED_MAX * 100))
        self.speed.setToolTip("Multiplier on the wait between inputs (base = 1.2 frames at the FPS from Settings).\n"
                              "Higher is faster; too high and the game starts dropping clicks. Works while drawing.")
        srow = QHBoxLayout()
        srow.setSpacing(4)
        self.speed_label = QLabel("1.00×")
        self.speed_label.setMinimumWidth(34)
        srow.addWidget(self.speed, 1)
        srow.addWidget(self.speed_label)
        form.addRow("Speed", srow)

        self.final_toggle = QCheckBox("Show final result")
        self.final_toggle.setToolTip("On: preview the finished image.\n"
                                     "Off: preview only the pixels placed so far (follows the timeline).\n"
                                     "Click-dragging the timeline always previews the progress.")
        form.addRow("", self.final_toggle)

        self.grid_toggle = QCheckBox("Show pixel grid")
        form.addRow("", self.grid_toggle)

        scroll = QScrollArea()
        scroll.setWidget(form_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(0)
        self.form_container = scroll

        # ---- vertical split: preview | handle | properties
        self.split = FoldSplitter()
        self.split.addWidget(self.preview)
        self.split.addWidget(self.form_container)
        self.split.setStretchFactor(0, 1)
        self.split.setStretchFactor(1, 2)
        self.split.splitterMoved.connect(self._on_split_moved)
        self.body.addWidget(self.split, 1)

        self.stats = QLabel("—")
        self.stats.setStyleSheet("color: #a0a3a8; font-size: 11px;")
        self.body.addWidget(self.stats)

        # ---- wiring
        self._load_adjustments(app.adjustments)
        self.final_toggle.setChecked(app.state.output_shows_final)
        self.palette.currentIndexChanged.connect(self._push)
        self.dither.toggled.connect(self._push)
        self.invert.toggled.connect(self._push)
        for s, _ in self.sliders.values():
            s.valueChanged.connect(self._push)
        self.alpha.valueChanged.connect(self._push)
        self.reset_button.clicked.connect(lambda: app.set_adjustments(Adjustments()))
        self.final_toggle.toggled.connect(self._on_final_toggled)
        self.grid_toggle.toggled.connect(self._on_grid_toggled)
        self._load_method(app.draw_method, app.draw_seed)
        self._load_color_order(app.color_order)
        self._load_speed(app.state.speed)
        self.speed.valueChanged.connect(self._on_speed_slider)
        app.speed_changed.connect(self._load_speed)
        app.pen_changed.connect(lambda _: self._update_stats())
        # everything that would rebuild the plan is locked while a draw is running; Speed stays live
        self._locked_while_running = [self.palette, self.dither, self.invert, self.alpha, self.reset_button,
                                      self.method, self.color_order, self.reroll_button] + \
                                     [s for s, _ in self.sliders.values()]
        self.method.currentIndexChanged.connect(self._on_method_changed)
        self.color_order.currentIndexChanged.connect(self._on_color_order_changed)
        app.color_order_changed.connect(self._load_color_order)
        self.reroll_button.clicked.connect(app.reroll_seed)
        app.draw_method_changed.connect(self._load_method)
        app.scrubbing.connect(self._on_scrubbing)

        app.output_changed.connect(self._on_output)
        app.adjustments_changed.connect(self._load_adjustments)
        app.drawer.progress.connect(self._on_progress)
        app.drawer.state_changed.connect(self._on_state)
        self._render_timer = QTimer(self, singleShot=True, interval=16)
        self._render_timer.timeout.connect(self._render)
        QTimer.singleShot(0, self._restore_split)

    # ---- split persistence -----------------------------------------------------------------
    def _restore_split(self):
        p = self.state.panel(self.panel_name)
        total = max(1, self.split.height() - HANDLE_H)
        sizes = p.get("split")
        if sizes and len(sizes) == 2 and sum(sizes) > 0:
            self.split._unfolded_sizes = [int(total * sizes[0] / sum(sizes)), int(total * sizes[1] / sum(sizes))]
        else:
            self.split._unfolded_sizes = [total // 3, total - total // 3]
        self.split.setSizes(self.split._unfolded_sizes)
        if p.get("folded"):
            self.split.folded = False
            self.split.toggle_fold()

    def _on_split_moved(self, *_):
        if not self.split.folded:
            self.state.panel(self.panel_name)["split"] = self.split.sizes()
            self._save_timer.start()

    def _persist(self):
        p = self.state.panel(self.panel_name)
        p["folded"] = self.split.folded
        if not self.split.folded:
            p["split"] = self.split.sizes()
        elif self.split._unfolded_sizes:
            p["split"] = self.split._unfolded_sizes
        super()._persist()

    # ---- adjustments <-> widgets ----------------------------------------------------------
    def _load_adjustments(self, adj: Adjustments):
        self._syncing = True
        idx = self.palette.findData(adj.palette_limit)
        self.palette.setCurrentIndex(idx if idx >= 0 else 0)
        self.dither.setChecked(adj.dither)
        self.invert.setChecked(adj.invert)
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
            invert=self.invert.isChecked(),
            alpha_threshold=self.alpha.value(),
        )
        for key, (s, val) in self.sliders.items():
            val.setText(f"{s.value() / 100:.2f}")
        self.alpha_label.setText(str(self.alpha.value()))
        self.app.set_adjustments(adj)

    # ---- draw order --------------------------------------------------------------------------------
    def _load_method(self, method: str, seed: int):
        self._syncing = True
        idx = self.method.findData(method)
        self.method.setCurrentIndex(idx if idx >= 0 else 0)
        self.method.setToolTip(self.method.itemData(self.method.currentIndex(), Qt.ToolTipRole) or "")
        self._syncing = False
        self._update_reroll()

    def _on_method_changed(self, *_):
        if not self._syncing:
            self.app.set_draw_method(self.method.currentData())

    def _load_color_order(self, order: str):
        self._syncing = True
        idx = self.color_order.findData(order)
        self.color_order.setCurrentIndex(idx if idx >= 0 else 0)
        self.color_order.setToolTip(self.color_order.itemData(self.color_order.currentIndex(), Qt.ToolTipRole) or "")
        self._syncing = False
        self._update_reroll()

    def _on_color_order_changed(self, *_):
        if not self._syncing:
            self.app.set_color_order(self.color_order.currentData())

    def _update_reroll(self):
        if not hasattr(self, "color_order"):
            return
        self.reroll_button.setEnabled(not self._running and
                                      is_random(self.method.currentData(), self.color_order.currentData()))

    # ---- speed -------------------------------------------------------------------------------------
    def _load_speed(self, speed: float):
        self._syncing = True
        self.speed.setValue(int(round(speed * 100)))
        self.speed_label.setText(f"{speed:.2f}×")
        self._syncing = False
        self._update_stats()

    def _on_speed_slider(self, value: int):
        self.speed_label.setText(f"{value / 100:.2f}×")
        if not self._syncing:
            self.app.set_speed(value / 100)

    # ---- preview ----------------------------------------------------------------------------------
    def _follows_timeline(self) -> bool:
        return self._scrubbing or not self.final_toggle.isChecked()

    def _on_scrubbing(self, active: bool):
        self._scrubbing = active
        self._render_timer.start()

    def _on_output(self, img, steps):
        self._index = min(self._index, len(steps))
        self._render_timer.start()
        self._update_stats()

    def _update_stats(self):
        steps = self.app.steps
        if self.app.output is None:
            self.stats.setText("—")
            return
        n_colors = len(color_boundaries(steps))
        eta = estimate_seconds(steps, self.app.calibration.get_frame_sleep_time(), self.app.pencil.pen)
        m, s = divmod(int(eta), 60)
        self.stats.setText(f"{n_colors} colors · {len(steps)} steps · ~{m}m {s:02d}s")

    def _on_progress(self, index: int):
        self._index = index
        if self._follows_timeline():
            self._render_timer.start()

    def _render(self):
        img = self.app.output
        if img is not None and self._follows_timeline():
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
        self._running = state == RUNNING
        for w in self._locked_while_running:
            w.setEnabled(not self._running)
        self._update_reroll()
