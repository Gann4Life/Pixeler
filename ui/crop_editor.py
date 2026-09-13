'''Shows the source image and a crop rectangle with 8 visible drag handles.

Drag a handle to resize (Shift = keep aspect ratio, Alt = symmetric around the
center), drag inside to move, drag on the empty area to draw a new rectangle.
Mouse wheel zooms around the cursor, middle/right-drag pans, middle
double-click (or the 0 key) fits the image again.
The crop is exposed normalized (0..1) so it is independent of image size.
The output is always square, so the centered square of the selection is what
gets used; the strips outside it are shaded and the square is dashed.
'''
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QImage, QPixmap, QFont
from PySide6.QtWidgets import QWidget

from core.pipeline import NormRect
from .widgets import hit_handle, resize_rect, move_rect, draw_handles, CURSORS, HANDLE_SIZE


def pil_to_qpixmap(img) -> QPixmap:
    rgba = img if img.mode == 'RGBA' else img.convert('RGBA')
    data = rgba.tobytes('raw', 'RGBA')
    qimg = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


class CropEditor(QWidget):
    crop_changed = Signal(object)   # NormRect, emitted on every drag update

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(120, 120)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
        self._pixmap = None
        self._crop = NormRect()
        self._editable = True
        # view (zoom is relative to "fit"; pan is a widget-pixel offset)
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self._pan_origin = None    # (widget pos, pan) at the start of a pan drag
        # interaction state
        self._mode = None          # 'handle' | 'move' | 'new'
        self._handle = None
        self._press_img = None     # QPointF in image coords
        self._rect0 = None         # QRectF in image coords at drag start

    # ---- public --------------------------------------------------------------------------
    def set_image(self, pil_image):
        self._pixmap = pil_to_qpixmap(pil_image) if pil_image is not None else None
        self.reset_view()

    # ---- view (zoom / pan) ---------------------------------------------------------------
    MAX_ZOOM = 32.0

    def reset_view(self):
        self._zoom = 1.0
        self._pan = QPointF(0, 0)
        self.update()

    def _set_zoom(self, zoom: float, anchor: QPointF = None):
        '''Zoom keeping the image point under `anchor` (widget coords) fixed.'''
        zoom = max(1.0, min(self.MAX_ZOOM, zoom))
        if anchor is None:
            anchor = QPointF(self.width() / 2, self.height() / 2)
        before = self._to_img(anchor)
        self._zoom = zoom
        after = self._to_img(anchor)
        s = self._fit()[0]
        self._pan += QPointF((after.x() - before.x()) * s, (after.y() - before.y()) * s)
        self._clamp_pan()
        self.update()

    def _clamp_pan(self):
        '''Keep the image covering the view: no panning when it fits, else stay within its edges.'''
        if not self._pixmap:
            return
        s = self._fit()[0]
        w, h = self._pixmap.width() * s, self._pixmap.height() * s
        lim_x = max(0.0, (w - self.width()) / 2)
        lim_y = max(0.0, (h - self.height()) / 2)
        self._pan = QPointF(max(-lim_x, min(lim_x, self._pan.x())), max(-lim_y, min(lim_y, self._pan.y())))

    def set_crop(self, crop: NormRect):
        self._crop = crop.clamped()
        self.update()

    def crop(self) -> NormRect:
        return self._crop

    def reset_crop(self):
        self.set_crop(NormRect())
        self.crop_changed.emit(self._crop)

    def set_editable(self, editable: bool):
        self._editable = editable
        self.setCursor(Qt.ArrowCursor)
        self.update()

    # ---- coordinate mapping (widget <-> image pixels) ---------------------------------
    def _fit(self):
        '''Returns (scale, offset_x, offset_y) that fits the image in the widget.'''
        if not self._pixmap:
            return 1.0, 0.0, 0.0
        w, h = self._pixmap.width(), self._pixmap.height()
        m = HANDLE_SIZE   # keep edge handles fully visible
        scale = min(max(1, self.width() - 2 * m) / w, max(1, self.height() - 2 * m) / h) * self._zoom
        return (scale, (self.width() - w * scale) / 2 + self._pan.x(),
                (self.height() - h * scale) / 2 + self._pan.y())

    def _img_rect(self) -> QRectF:
        return QRectF(0, 0, self._pixmap.width(), self._pixmap.height()) if self._pixmap else QRectF()

    def _to_img(self, p: QPointF) -> QPointF:
        s, ox, oy = self._fit()
        return QPointF((p.x() - ox) / s, (p.y() - oy) / s)

    def _to_widget_rect(self, r: QRectF) -> QRectF:
        s, ox, oy = self._fit()
        return QRectF(ox + r.left() * s, oy + r.top() * s, r.width() * s, r.height() * s)

    def _crop_img_rect(self) -> QRectF:
        ir = self._img_rect()
        c = self._crop
        return QRectF(c.x * ir.width(), c.y * ir.height(), c.w * ir.width(), c.h * ir.height())

    def _set_crop_from_img_rect(self, r: QRectF):
        ir = self._img_rect()
        if ir.width() <= 0 or ir.height() <= 0:
            return
        self._crop = NormRect(r.left() / ir.width(), r.top() / ir.height(),
                              r.width() / ir.width(), r.height() / ir.height()).clamped()
        self.crop_changed.emit(self._crop)
        self.update()

    # ---- painting --------------------------------------------------------------------------
    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(23, 24, 26))
        if not self._pixmap:
            p.setPen(QColor(120, 123, 128))
            p.drawText(self.rect(), Qt.AlignCenter, "No image\nLoad a file or paste from clipboard")
            return
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        target = self._to_widget_rect(self._img_rect())
        p.drawPixmap(target, self._pixmap, QRectF(self._pixmap.rect()))

        crop_w = self._to_widget_rect(self._crop_img_rect())
        # dim everything outside the crop
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 140))
        for r in _outside(target, crop_w):
            p.drawRect(r)
        # the output is square: shade the strips of the selection that get cropped to fit
        l, t, r_, b = self._crop.to_square_box(self._pixmap.width(), self._pixmap.height())
        square_w = self._to_widget_rect(QRectF(l, t, r_ - l, b - t))
        p.setBrush(QColor(0, 0, 0, 70))
        for r in _outside(crop_w, square_w):
            p.drawRect(r)
        pen = QPen(QColor(255, 255, 255), 1)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(crop_w)
        if square_w != crop_w:
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.drawRect(square_w)
            pen.setStyle(Qt.SolidLine)
        # rule-of-thirds guide while dragging
        if self._mode:
            pen.setColor(QColor(255, 255, 255, 80))
            p.setPen(pen)
            for i in (1, 2):
                x = crop_w.left() + crop_w.width() * i / 3
                y = crop_w.top() + crop_w.height() * i / 3
                p.drawLine(QPointF(x, crop_w.top()), QPointF(x, crop_w.bottom()))
                p.drawLine(QPointF(crop_w.left(), y), QPointF(crop_w.right(), y))
        if self._editable:
            draw_handles(p, crop_w, HANDLE_SIZE, active=self._handle if self._mode == 'handle' else None)
        if self._zoom > 1.0:
            font = QFont()
            font.setPointSize(8)
            p.setFont(font)
            text = f"{self._zoom:.1f}×  (middle double-click or 0 = fit)"
            tw = p.fontMetrics().horizontalAdvance(text) + 10
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 150))
            p.drawRoundedRect(QRectF(4, 4, tw, 16), 3, 3)
            p.setPen(QColor(220, 222, 226))
            p.drawText(QRectF(9, 4, tw, 16), Qt.AlignVCenter | Qt.AlignLeft, text)

    # ---- mouse ----------------------------------------------------------------------------------
    def mousePressEvent(self, e):
        if e.button() in (Qt.MiddleButton, Qt.RightButton) and self._pixmap:
            self._pan_origin = (e.position(), QPointF(self._pan))
            self.setCursor(Qt.ClosedHandCursor)
            return
        if e.button() != Qt.LeftButton or not self._pixmap or not self._editable:
            return
        pos = e.position()
        crop_w = self._to_widget_rect(self._crop_img_rect())
        handle = hit_handle(crop_w, pos)
        self._press_img = self._to_img(pos)
        self._rect0 = self._crop_img_rect()
        if handle:
            self._mode, self._handle = 'handle', handle
        elif crop_w.contains(pos):
            self._mode = 'move'
        elif self._to_widget_rect(self._img_rect()).contains(pos):
            self._mode = 'new'
        else:
            self._mode = None
        self.update()

    def mouseMoveEvent(self, e):
        if self._pan_origin is not None:
            start, pan0 = self._pan_origin
            self._pan = pan0 + (e.position() - start)
            self._clamp_pan()
            self.update()
            return
        if not self._pixmap or not self._editable:
            return
        pos = e.position()
        if not self._mode:
            crop_w = self._to_widget_rect(self._crop_img_rect())
            h = hit_handle(crop_w, pos)
            self.setCursor(CURSORS[h] if h else Qt.SizeAllCursor if crop_w.contains(pos) else Qt.CrossCursor)
            return
        keep_aspect = bool(e.modifiers() & Qt.ShiftModifier)
        symmetric = bool(e.modifiers() & Qt.AltModifier)
        cur = self._to_img(pos)
        delta = cur - self._press_img
        bounds = self._img_rect()
        if self._mode == 'handle':
            r = resize_rect(self._rect0, self._handle, delta, keep_aspect=keep_aspect,
                            symmetric=symmetric, bounds=bounds, min_size=1.0)
        elif self._mode == 'move':
            r = move_rect(self._rect0, delta, bounds)
        else:  # new rectangle from the press point
            a = self._press_img
            if symmetric:
                r = QRectF(a.x() - abs(delta.x()), a.y() - abs(delta.y()), 2 * abs(delta.x()), 2 * abs(delta.y()))
            else:
                r = QRectF(a, cur).normalized()
            if keep_aspect and r.width() > 0 and r.height() > 0:
                side = max(r.width(), r.height())
                sx = 1 if cur.x() >= a.x() else -1
                sy = 1 if cur.y() >= a.y() else -1
                if symmetric:
                    r = QRectF(a.x() - side, a.y() - side, 2 * side, 2 * side)
                else:
                    r = QRectF(a, QPointF(a.x() + sx * side, a.y() + sy * side)).normalized()
            r = r.intersected(bounds)
            if r.width() < 1 or r.height() < 1:
                return
        self._set_crop_from_img_rect(r)

    def mouseReleaseEvent(self, e):
        if self._pan_origin is not None and e.button() in (Qt.MiddleButton, Qt.RightButton):
            self._pan_origin = None
            self.setCursor(Qt.ArrowCursor)
            return
        if self._mode:
            self._mode = None
            self._handle = None
            self.update()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self.reset_view()

    def wheelEvent(self, e):
        if not self._pixmap:
            return
        steps = e.angleDelta().y() / 120.0
        self._set_zoom(self._zoom * (1.25 ** steps), e.position())
        e.accept()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_0, Qt.Key_Home):
            self.reset_view()
        else:
            super().keyPressEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._clamp_pan()

    def leaveEvent(self, e):
        self.setCursor(Qt.ArrowCursor)


def _outside(outer: QRectF, inner: QRectF):
    '''Four rects covering `outer` minus `inner`.'''
    inner = inner.intersected(outer)
    return [
        QRectF(outer.left(), outer.top(), outer.width(), inner.top() - outer.top()),
        QRectF(outer.left(), inner.bottom(), outer.width(), outer.bottom() - inner.bottom()),
        QRectF(outer.left(), inner.top(), inner.left() - outer.left(), inner.height()),
        QRectF(inner.right(), inner.top(), outer.right() - inner.right(), inner.height()),
    ]
