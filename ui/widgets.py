'''Shared bits: rectangle-with-handles math (used by the crop editor and the
calibration overlay), handle painting, and a hotkey capture widget.'''
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPen, QBrush, QKeySequence
from PySide6.QtWidgets import QKeySequenceEdit

# Handle ids, clockwise from top-left. Edges are single letters.
HANDLES = ('tl', 't', 'tr', 'r', 'br', 'b', 'bl', 'l')
CURSORS = {
    'tl': Qt.SizeFDiagCursor, 'br': Qt.SizeFDiagCursor,
    'tr': Qt.SizeBDiagCursor, 'bl': Qt.SizeBDiagCursor,
    't': Qt.SizeVerCursor, 'b': Qt.SizeVerCursor,
    'l': Qt.SizeHorCursor, 'r': Qt.SizeHorCursor,
}
HANDLE_SIZE = 9


def handle_points(rect: QRectF) -> dict:
    cx, cy = rect.center().x(), rect.center().y()
    return {
        'tl': rect.topLeft(), 't': QPointF(cx, rect.top()), 'tr': rect.topRight(),
        'r': QPointF(rect.right(), cy), 'br': rect.bottomRight(),
        'b': QPointF(cx, rect.bottom()), 'bl': rect.bottomLeft(), 'l': QPointF(rect.left(), cy),
    }


def hit_handle(rect: QRectF, pos: QPointF, size: float = HANDLE_SIZE):
    '''Returns the handle id under `pos` (corners win over edges) or None.'''
    half = size / 2 + 2
    pts = handle_points(rect)
    for name in ('tl', 'tr', 'br', 'bl', 't', 'r', 'b', 'l'):
        p = pts[name]
        if abs(pos.x() - p.x()) <= half and abs(pos.y() - p.y()) <= half:
            return name
    return None


def resize_rect(rect0: QRectF, handle: str, delta: QPointF, *, keep_aspect=False,
                symmetric=False, bounds: QRectF = None, min_size: float = 2.0) -> QRectF:
    '''Rect after dragging `handle` by `delta` from the drag-start rect `rect0`.

    keep_aspect: preserve rect0's width/height ratio (pass a square rect0 to keep 1:1).
    symmetric:   the opposite side/corner mirrors the movement around the center.
    bounds:      result is kept inside (aspect is preserved by shrinking if needed).
    '''
    l, t, r, b = rect0.left(), rect0.top(), rect0.right(), rect0.bottom()
    dx, dy = delta.x(), delta.y()
    has_l, has_r = 'l' in handle, 'r' in handle
    has_t, has_b = 't' in handle, 'b' in handle
    ratio = rect0.width() / rect0.height() if rect0.height() > 0 else 1.0

    if has_l: l += dx
    if has_r: r += dx
    if has_t: t += dy
    if has_b: b += dy
    if symmetric:
        if has_l: r -= dx
        if has_r: l -= dx
        if has_t: b -= dy
        if has_b: t -= dy

    # Never invert: keep the moving side(s) on the correct side of the anchor.
    if r - l < min_size:
        if has_l and not has_r: l = r - min_size
        elif has_r and not has_l: r = l + min_size
        else:
            c = (l + r) / 2; l, r = c - min_size / 2, c + min_size / 2
    if b - t < min_size:
        if has_t and not has_b: t = b - min_size
        elif has_b and not has_t: b = t + min_size
        else:
            c = (t + b) / 2; t, b = c - min_size / 2, c + min_size / 2

    if keep_aspect:
        w, h = r - l, b - t
        horizontal_only = (has_l or has_r) and not (has_t or has_b)
        vertical_only = (has_t or has_b) and not (has_l or has_r)
        if horizontal_only:
            h = w / ratio
        elif vertical_only:
            w = h * ratio
        else:  # corner: follow the axis the user moved most
            if abs(w / rect0.width() - 1) >= abs(h / rect0.height() - 1):
                h = w / ratio
            else:
                w = h * ratio
        l, t, r, b = _apply_size(rect0, handle, symmetric, w, h, l, t, r, b)

    out = QRectF(QPointF(l, t), QPointF(r, b)).normalized()
    if bounds is not None:
        out = _fit_in_bounds(out, rect0, handle, symmetric, keep_aspect, bounds)
    return out


def _apply_size(rect0, handle, symmetric, w, h, l, t, r, b):
    '''Re-anchor a rect of size (w, h) according to which handle is being dragged.'''
    has_l, has_r = 'l' in handle, 'r' in handle
    has_t, has_b = 't' in handle, 'b' in handle
    cx, cy = rect0.center().x(), rect0.center().y()
    # Horizontal placement
    if symmetric or not (has_l or has_r):
        l, r = cx - w / 2, cx + w / 2
    elif has_l:
        l = r - w
    else:
        r = l + w
    # Vertical placement
    if symmetric or not (has_t or has_b):
        t, b = cy - h / 2, cy + h / 2
    elif has_t:
        t = b - h
    else:
        b = t + h
    return l, t, r, b


def _fit_in_bounds(rect, rect0, handle, symmetric, keep_aspect, bounds):
    if bounds.contains(rect):
        return rect
    if not keep_aspect:
        return rect.intersected(bounds) if rect.intersects(bounds) else rect0
    # Shrink around the anchor until it fits.
    has_l, has_r = 'l' in handle, 'r' in handle
    has_t, has_b = 't' in handle, 'b' in handle
    if symmetric:
        ax, ay = rect0.center().x(), rect0.center().y()
    else:
        ax = rect0.right() if has_l else rect0.left() if has_r else rect0.center().x()
        ay = rect0.bottom() if has_t else rect0.top() if has_b else rect0.center().y()
    # Available room from the anchor in each direction, given how the rect extends from it.
    def room(a, lo, hi, extends_neg, extends_pos, size):
        if extends_neg and extends_pos:   # centered on anchor
            return 2 * min(a - lo, hi - a)
        if extends_neg:
            return a - lo
        return hi - a
    ext_l = rect.left() < ax - 1e-6
    ext_r = rect.right() > ax + 1e-6
    ext_t = rect.top() < ay - 1e-6
    ext_b = rect.bottom() > ay + 1e-6
    max_w = room(ax, bounds.left(), bounds.right(), ext_l, ext_r, rect.width())
    max_h = room(ay, bounds.top(), bounds.bottom(), ext_t, ext_b, rect.height())
    scale = min(1.0, max_w / rect.width() if rect.width() else 1, max_h / rect.height() if rect.height() else 1)
    w, h = rect.width() * scale, rect.height() * scale
    l = ax - w if (ext_l and not ext_r) else ax - w / 2 if (ext_l and ext_r) else ax
    t = ay - h if (ext_t and not ext_b) else ay - h / 2 if (ext_t and ext_b) else ay
    return QRectF(l, t, w, h).intersected(bounds)


def move_rect(rect0: QRectF, delta: QPointF, bounds: QRectF = None) -> QRectF:
    out = rect0.translated(delta)
    if bounds is not None:
        if out.left() < bounds.left(): out.moveLeft(bounds.left())
        if out.top() < bounds.top(): out.moveTop(bounds.top())
        if out.right() > bounds.right(): out.moveRight(bounds.right())
        if out.bottom() > bounds.bottom(): out.moveBottom(bounds.bottom())
    return out


def draw_handles(painter, rect: QRectF, size: float = HANDLE_SIZE, color=QColor(255, 255, 255), active: str = None):
    painter.save()
    for name, p in handle_points(rect).items():
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        painter.setBrush(QBrush(QColor(255, 200, 0) if name == active else color))
        painter.drawRect(QRectF(p.x() - size / 2, p.y() - size / 2, size, size))
    painter.restore()


# ---- hotkey capture ---------------------------------------------------------------
_QT_TO_KEYBOARD = {
    'return': 'enter', 'meta': 'windows', 'del': 'delete', 'ins': 'insert',
    'pgup': 'page up', 'pgdown': 'page down', 'esc': 'esc',
}


def qt_to_keyboard(seq: QKeySequence) -> str:
    '''"Ctrl+Shift+Space" -> "ctrl+shift+space" (the `keyboard` module's format).'''
    text = seq.toString(QKeySequence.PortableText)
    first = text.split(", ")[0] if text else ""
    parts = [p.strip().lower() for p in first.split("+") if p.strip()]
    return "+".join(_QT_TO_KEYBOARD.get(p, p) for p in parts)


def keyboard_to_qt(key: str) -> QKeySequence:
    inv = {v: k for k, v in _QT_TO_KEYBOARD.items()}
    parts = [inv.get(p, p).capitalize() for p in (key or "").split("+") if p]
    return QKeySequence("+".join(parts))


class KeyCapture(QKeySequenceEdit):
    '''Records a single key combination and exposes it in `keyboard` format.'''

    def __init__(self, key: str = "", parent=None):
        super().__init__(parent)
        self.setMaximumSequenceLength(1)
        self.setClearButtonEnabled(True)
        self.set_key(key)

    def set_key(self, key: str):
        self.setKeySequence(keyboard_to_qt(key))

    def key(self) -> str:
        return qt_to_keyboard(self.keySequence())
