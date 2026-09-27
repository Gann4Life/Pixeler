'''Fullscreen translucent overlay to calibrate the game's canvas and color picker.
See docs/calibration-overlay.md.

Drag once to define a square canvas (32x32 red dots show every cell center),
then fine-tune with the corner/edge handles (always square) or move it.
Drag the three crosshair markers onto the color picker buttons. Enter saves,
Esc cancels. Coordinates are physical screen pixels (HiDPI scaling is off).
'''
from PySide6.QtCore import Qt, QRectF, QPointF, QPoint, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QCursor, QGuiApplication, QFont
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton

from core.actuator import PencilTool
from core.audio import Audio
from core.calibration import CalibrationModel, GRID
from .widgets import hit_handle, resize_rect, move_rect, draw_handles, CURSORS
from .floating_panel import STYLE

MARKERS = (
    ("colorCord", "Color button"),
    ("inputCord", "Hex input"),
    ("closeCord", "Close button"),
)
MARKER_HIT = 14


class CalibrationOverlay(QWidget):
    saved = Signal()
    closed = Signal()

    def __init__(self, model: CalibrationModel, pencil: PencilTool = None):
        super().__init__(None)
        self.model = model
        self.pencil = pencil
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet(STYLE)
        self.setCursor(Qt.CrossCursor)

        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.setGeometry(screen.geometry())
        self.origin = screen.geometry().topLeft()   # local -> physical: add origin

        # ---- working copies (local coordinates)
        self.area = None                       # QRectF or None
        if model.area:
            x0, y0, s = model.area
            self.area = QRectF(x0 - self.origin.x(), y0 - self.origin.y(), s, s)
        self.markers = {}
        for key, _ in MARKERS:
            v = list(getattr(model, key))
            if v != [0, 0]:
                self.markers[key] = QPointF(v[0] - self.origin.x(), v[1] - self.origin.y())
        self._place_missing_markers()

        # ---- interaction state
        self._mode = None       # 'new' | 'handle' | 'move' | 'marker'
        self._handle = None
        self._marker = None
        self._press = None
        self._rect0 = None
        self._marker0 = None
        self.focused = 'area'   # 'area' or a marker key, for arrow-key nudging

        # ---- toolbar
        self.toolbar = QWidget(self, objectName="panelRoot")
        self.toolbar.setStyleSheet(STYLE + "QWidget#panelRoot { border-radius: 6px; }")
        tb = QHBoxLayout(self.toolbar)
        tb.setContentsMargins(10, 6, 10, 6)
        self.hint = QLabel()
        tb.addWidget(self.hint)
        tb.addSpacing(12)
        self.test_button = QPushButton("Test")
        self.test_button.setToolTip("Move the mouse to the corner cells and the three buttons (no clicks)")
        self.test_button.clicked.connect(self._test)
        self.save_button = QPushButton("Save  (Enter)")
        self.save_button.clicked.connect(self.save)
        self.cancel_button = QPushButton("Cancel  (Esc)")
        self.cancel_button.clicked.connect(self.close)
        for b in (self.test_button, self.save_button, self.cancel_button):
            tb.addWidget(b)
        self.toolbar.adjustSize()
        self._place_toolbar()
        self._update_hint()

    # ---- helpers ------------------------------------------------------------------------------
    def _place_toolbar(self):
        self.toolbar.adjustSize()
        self.toolbar.move((self.width() - self.toolbar.width()) // 2, 16)

    def _place_missing_markers(self):
        base = self.area.topRight() + QPointF(40, 0) if self.area else QPointF(self.width() / 2, self.height() / 2)
        for i, (key, _) in enumerate(MARKERS):
            if key not in self.markers:
                self.markers[key] = base + QPointF(0, 40 * i)

    def _update_hint(self):
        if self.area is None:
            self.hint.setText("Step 1: drag a square over the game's drawing canvas")
        else:
            self.hint.setText("Adjust the square with its handles (arrows nudge, Shift = ×10), "
                              "then drag the three markers onto the color picker buttons")
        self._place_toolbar()

    def _bounds(self) -> QRectF:
        return QRectF(self.rect())

    def _marker_at(self, pos: QPointF):
        for key, p in self.markers.items():
            if abs(pos.x() - p.x()) <= MARKER_HIT and abs(pos.y() - p.y()) <= MARKER_HIT:
                return key
        return None

    # ---- painting --------------------------------------------------------------------------------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.fillRect(self.rect(), QColor(0, 0, 0, 64))

        if self.area is not None:
            r = self.area
            # clear the tint inside the canvas so the game's grid is easy to see
            p.setCompositionMode(QPainter.CompositionMode_Source)
            p.fillRect(r, QColor(0, 0, 0, 0))
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            cell = r.width() / GRID
            pen = QPen(QColor(255, 255, 255, 60), 1)
            pen.setCosmetic(True)
            p.setPen(pen)
            for k in range(GRID + 1):
                x = r.left() + k * cell
                y = r.top() + k * cell
                p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
                p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            dot = QPen(QColor(255, 40, 40), 3)
            dot.setCapStyle(Qt.RoundCap)
            p.setPen(dot)
            pts = [QPointF(r.left() + (i + 0.5) * cell, r.top() + (j + 0.5) * cell)
                   for j in range(GRID) for i in range(GRID)]
            p.drawPoints(pts)
            outline = QPen(QColor(255, 255, 255) if self.focused == 'area' else QColor(200, 200, 200), 2)
            p.setPen(outline)
            p.setBrush(Qt.NoBrush)
            p.drawRect(r)
            draw_handles(p, r, 11, active=self._handle if self._mode == 'handle' else None)
            p.setPen(QColor(255, 255, 255))
            p.drawText(QPointF(r.left(), r.top() - 6), f"canvas {int(r.width())}px  ·  cell {cell:.1f}px")

        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        p.setFont(font)
        for key, label in MARKERS:
            c = self.markers[key]
            color = QColor(255, 220, 0) if self.focused == key else QColor(80, 200, 255)
            pen = QPen(color, 2)
            p.setPen(pen)
            p.drawLine(QPointF(c.x() - 14, c.y()), QPointF(c.x() + 14, c.y()))
            p.drawLine(QPointF(c.x(), c.y() - 14), QPointF(c.x(), c.y() + 14))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, 8, 8)
            p.setPen(QColor(0, 0, 0, 160))
            p.setBrush(QColor(0, 0, 0, 160))
            tw = p.fontMetrics().horizontalAdvance(label) + 10
            p.drawRoundedRect(QRectF(c.x() + 12, c.y() - 26, tw, 18), 3, 3)
            p.setPen(color)
            p.drawText(QPointF(c.x() + 17, c.y() - 12), label)

    # ---- mouse ----------------------------------------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        pos = e.position()
        self._press = pos
        self.setFocus()
        m = self._marker_at(pos)
        if m:
            self._mode, self._marker, self._marker0 = 'marker', m, QPointF(self.markers[m])
            self.focused = m
        elif self.area is not None and hit_handle(self.area, pos, 11):
            self._mode, self._handle = 'handle', hit_handle(self.area, pos, 11)
            self._rect0 = QRectF(self.area)
            self.focused = 'area'
        elif self.area is not None and self.area.contains(pos):
            self._mode, self._rect0 = 'move', QRectF(self.area)
            self.focused = 'area'
        else:
            self._mode = 'new'
            self.focused = 'area'
        self.update()

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._mode is None:
            m = self._marker_at(pos)
            h = hit_handle(self.area, pos, 11) if self.area is not None else None
            if m or (self.area is not None and self.area.contains(pos) and not h):
                self.setCursor(Qt.SizeAllCursor)
            elif h:
                self.setCursor(CURSORS[h])
            else:
                self.setCursor(Qt.CrossCursor)
            return
        delta = pos - self._press
        if self._mode == 'marker':
            self.markers[self._marker] = self._marker0 + delta
        elif self._mode == 'handle':
            self.area = resize_rect(self._rect0, self._handle, delta, keep_aspect=True,
                                    symmetric=bool(e.modifiers() & Qt.AltModifier),
                                    bounds=self._bounds(), min_size=GRID)
        elif self._mode == 'move':
            self.area = move_rect(self._rect0, delta, self._bounds())
        elif self._mode == 'new':
            side = max(abs(delta.x()), abs(delta.y()))
            if side < 2:
                return
            sx = 1 if delta.x() >= 0 else -1
            sy = 1 if delta.y() >= 0 else -1
            a = self._press
            self.area = QRectF(a, QPointF(a.x() + sx * side, a.y() + sy * side)).normalized().intersected(self._bounds())
            # keep it square after clamping to the screen
            s = min(self.area.width(), self.area.height())
            self.area = QRectF(self.area.left() if sx > 0 else self.area.right() - s,
                               self.area.top() if sy > 0 else self.area.bottom() - s, s, s)
        self._update_hint()
        self.update()

    def mouseReleaseEvent(self, e):
        if self._mode == 'new' and self.area is not None:
            Audio.play_xpop()
            self._place_missing_markers()
        self._mode = self._handle = self._marker = None
        self._update_hint()
        self.update()

    # ---- keyboard -----------------------------------------------------------------------------------
    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Escape:
            self.close()
            return
        if k in (Qt.Key_Return, Qt.Key_Enter):
            self.save()
            return
        step = 10 if e.modifiers() & Qt.ShiftModifier else 1
        d = {Qt.Key_Left: QPointF(-step, 0), Qt.Key_Right: QPointF(step, 0),
             Qt.Key_Up: QPointF(0, -step), Qt.Key_Down: QPointF(0, step)}.get(k)
        if d is None:
            super().keyPressEvent(e)
            return
        if self.focused == 'area' and self.area is not None:
            self.area = move_rect(self.area, d, self._bounds())
        elif self.focused in self.markers:
            self.markers[self.focused] += d
        self.update()

    # ---- test / save ----------------------------------------------------------------------------------
    def _test(self):
        if self.area is None or self.pencil is None:
            Audio.play_error()
            return
        r = self.area
        cell = r.width() / GRID
        targets = [
            (r.left() + 0.5 * cell, r.top() + 0.5 * cell),
            (r.right() - 0.5 * cell, r.top() + 0.5 * cell),
            (r.right() - 0.5 * cell, r.bottom() - 0.5 * cell),
            (r.left() + 0.5 * cell, r.bottom() - 0.5 * cell),
        ] + [(self.markers[k].x(), self.markers[k].y()) for k, _ in MARKERS]
        ox, oy = self.origin.x(), self.origin.y()

        def go(i=0):
            if i >= len(targets):
                Audio.play_ding()
                return
            x, y = targets[i]
            self.pencil.move_to(x + ox, y + oy)
            QTimer.singleShot(450, lambda: go(i + 1))
        go()

    def save(self):
        if self.area is None:
            Audio.play_error()
            self.hint.setText("Define the canvas square first.")
            return
        ox, oy = self.origin.x(), self.origin.y()
        self.model.area = (self.area.left() + ox, self.area.top() + oy, self.area.width())
        for key, _ in MARKERS:
            m = self.markers[key]
            setattr(self.model, key, [int(round(m.x() + ox)), int(round(m.y() + oy))])
        if self.model.fps <= 0:
            self.model.fps = 60
        if self.model.safe_save():
            Audio.play_ding()
            self.saved.emit()
            self.close()
        else:
            self.hint.setText("Could not save — check that every value is set.")

    def closeEvent(self, e):
        self.closed.emit()
        super().closeEvent(e)
