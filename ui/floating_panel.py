'''Base class for the floating panels: frameless, always on top, draggable by its
title bar, resizable from every edge/corner, foldable down to the title bar (the ▾ at
the left, or double-click the title), with a ⋮ menu (opacity, always-on-top, reset
position, hide, quit). ✕ quits the app. Geometry and the fold are persisted to UiState.'''
from PySide6.QtCore import Qt, QPoint, QRect, QTimer, QEvent, Signal
from PySide6.QtGui import QAction, QGuiApplication
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton,
                               QMenu, QSlider, QWidgetAction)

from core.state import UiState, DEFAULT_PANELS

RESIZE_MARGIN = 6
TITLE_HEIGHT = 26
FOLDED_HEIGHT = TITLE_HEIGHT + 2 * RESIZE_MARGIN
QWIDGETSIZE_MAX = 16777215

STYLE = '''
QWidget#panelRoot { background: #202225; border: 1px solid #3a3d42; }
QWidget#titleBar { background: #2b2d31; }
QLabel { color: #e3e5e8; }
QLabel#title { font-weight: bold; padding-left: 6px; }
QToolButton { color: #e3e5e8; background: transparent; border: none; padding: 2px 6px; font-size: 14px; }
QToolButton:hover { background: #3a3d42; border-radius: 3px; }
QToolButton:checked { background: #4a4d55; border-radius: 3px; }
QToolButton:disabled { color: #6d7075; }
QPushButton { color: #e3e5e8; background: #35383d; border: 1px solid #45484e; border-radius: 3px; padding: 3px 8px; }
QPushButton:hover { background: #45484e; }
QPushButton:disabled { color: #6d7075; }
QSlider { background: transparent; border: none; }
QSlider::groove:horizontal { height: 4px; background: #45484e; border-radius: 2px; }
QSlider::handle:horizontal { width: 12px; margin: -5px 0; background: #e3e5e8; border-radius: 6px; }
QSlider::sub-page:horizontal { background: #5b8def; border-radius: 2px; }
QSlider::handle:horizontal:disabled { background: #6d7075; }
QCheckBox, QSpinBox, QDoubleSpinBox, QComboBox { color: #e3e5e8; background: transparent; }
QCheckBox::indicator { width: 13px; height: 13px; border: 1px solid #5a5d63; border-radius: 3px; background: #2b2d31; }
QCheckBox::indicator:checked { background: #5b8def; border-color: #5b8def; }
QScrollArea, QScrollArea > QWidget > QWidget, QAbstractScrollArea { background: #202225; border: none; }
QScrollBar:vertical { background: #202225; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #45484e; border-radius: 4px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #5a5d63; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: #202225; height: 8px; margin: 0; }
QScrollBar::handle:horizontal { background: #45484e; border-radius: 4px; min-width: 24px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit, QKeySequenceEdit { background: #2b2d31; border: 1px solid #45484e; border-radius: 3px; padding: 1px 4px; color: #e3e5e8; }
QComboBox QAbstractItemView { background: #2b2d31; color: #e3e5e8; selection-background-color: #5b8def; }
QMenu { background: #2b2d31; color: #e3e5e8; border: 1px solid #45484e; }
QMenu::item:selected { background: #5b8def; }
QToolTip { background: #2b2d31; color: #e3e5e8; border: 1px solid #45484e; }
QGraphicsView { background: #17181a; border: 1px solid #3a3d42; }
QDialog { background: #202225; }
QGroupBox { color: #e3e5e8; border: 1px solid #3a3d42; border-radius: 4px; margin-top: 8px; padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; }
QListWidget { background: #17181a; border: 1px solid #3a3d42; color: #e3e5e8; outline: none; }
QListWidget::item { padding: 3px 6px; }
QListWidget::item:selected { background: #5b8def; color: #ffffff; }
QListWidget::item:hover:!selected { background: #2b2d31; }
'''


class FloatingPanel(QWidget):
    quit_requested = Signal()

    def __init__(self, name: str, title: str, state: UiState, parent=None, min_size=(240, 200)):
        super().__init__(parent)
        self.panel_name = name
        self.state = state
        self.setObjectName("panelRoot")
        self.setWindowTitle(f"Pixeler — {title}")
        self.setMinimumSize(*min_size)
        self.setMouseTracking(True)
        self.setStyleSheet(STYLE)
        self._apply_flags(self.state.panel(name).get("on_top", True))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(RESIZE_MARGIN, RESIZE_MARGIN, RESIZE_MARGIN, RESIZE_MARGIN)
        outer.setSpacing(0)

        # ---- title bar
        self.title_bar = QWidget(objectName="titleBar")
        self.title_bar.setFixedHeight(TITLE_HEIGHT)
        self.title_bar.installEventFilter(self)
        tb = QHBoxLayout(self.title_bar)
        tb.setContentsMargins(0, 0, 2, 0)
        tb.setSpacing(0)
        self.fold_button = QToolButton(text="▾", toolTip="Fold / unfold this panel  (or double-click the title)")
        self.fold_button.clicked.connect(self.toggle_fold)
        tb.addWidget(self.fold_button)
        self.title_label = QLabel(title, objectName="title")
        tb.addWidget(self.title_label)
        tb.addStretch(1)
        self.title_buttons = tb   # subclasses insert extra buttons via add_title_button()

        self.menu_button = QToolButton(text="⋮", toolTip="Panel options (opacity, always on top…)")
        self.menu_button.setPopupMode(QToolButton.InstantPopup)
        self.menu_button.setMenu(self._build_menu())
        self.menu_button.setStyleSheet("QToolButton::menu-indicator { image: none; }")
        tb.addWidget(self.menu_button)

        self.close_button = QToolButton(text="✕", toolTip="Quit Pixeler")
        self.close_button.clicked.connect(self.quit_requested.emit)
        tb.addWidget(self.close_button)
        outer.addWidget(self.title_bar)

        # ---- body for subclasses
        self.body_widget = QWidget()
        self.body = QVBoxLayout(self.body_widget)
        self.body.setContentsMargins(6, 6, 6, 6)
        self.body.setSpacing(6)
        outer.addWidget(self.body_widget, 1)

        # ---- drag / resize bookkeeping
        self._drag_origin = None       # QPoint (global) when dragging the title bar
        self._drag_start_geo = None
        self._resize_edges = None      # set of 'l','r','t','b'
        self.folded = False
        self._unfolded_height = None   # what to grow back to (also what gets persisted while folded)
        self._unfolded_min_height = self.minimumHeight()
        self._save_timer = QTimer(self, singleShot=True, interval=400)
        self._save_timer.timeout.connect(self._persist)

        self.restore_geometry()

    # ---- title bar helpers ----------------------------------------------------------
    def add_title_button(self, text: str, tooltip: str, slot) -> QToolButton:
        btn = QToolButton(text=text, toolTip=tooltip)
        btn.clicked.connect(slot)
        # insert before the ⋮ button
        self.title_buttons.insertWidget(self.title_buttons.count() - 2, btn)
        return btn

    def add_menu_action(self, text: str, slot) -> QAction:
        '''Adds an entry to the ⋮ menu, just above "Hide this panel".'''
        action = QAction(text, self.menu_button.menu())
        action.triggered.connect(slot)
        self.menu_button.menu().insertAction(self.hide_action, action)
        return action

    def _build_menu(self) -> QMenu:
        menu = QMenu(self)
        label = QLabel("  Opacity")
        la = QWidgetAction(menu)
        la.setDefaultWidget(label)
        menu.addAction(la)

        self.opacity_slider = QSlider(Qt.Horizontal, minimum=20, maximum=100)
        self.opacity_slider.setFixedWidth(160)
        self.opacity_slider.setValue(int(self.state.panel(self.panel_name).get("opacity", 1.0) * 100))
        self.opacity_slider.valueChanged.connect(self._on_opacity)
        sa = QWidgetAction(menu)
        sa.setDefaultWidget(self.opacity_slider)
        menu.addAction(sa)
        menu.addSeparator()

        self.on_top_action = QAction("Always on top", menu, checkable=True)
        self.on_top_action.setChecked(self.state.panel(self.panel_name).get("on_top", True))
        self.on_top_action.toggled.connect(self._on_top_toggled)
        menu.addAction(self.on_top_action)

        reset = QAction("Reset position and size", menu)
        reset.triggered.connect(self.reset_geometry)
        menu.addAction(reset)
        menu.addSeparator()

        self.hide_action = QAction("Hide this panel", menu)
        self.hide_action.triggered.connect(self.hide)
        menu.addAction(self.hide_action)

        quit_action = QAction("Quit Pixeler", menu)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)
        return menu

    # ---- fold ---------------------------------------------------------------------------------
    def toggle_fold(self):
        self.set_folded(not self.folded)

    def set_folded(self, folded: bool):
        '''Folded = title bar only; the body and the height come back on unfold.'''
        if folded == self.folded:
            return
        self.folded = folded
        if folded:
            self._unfolded_height = self.height()
            self._unfolded_min_height = self.minimumHeight()
            self.body_widget.hide()
            self.setMinimumHeight(FOLDED_HEIGHT)
            self.setFixedHeight(FOLDED_HEIGHT)
        else:
            self.setMaximumHeight(QWIDGETSIZE_MAX)
            self.setMinimumHeight(self._unfolded_min_height)
            self.body_widget.show()
            self.resize(self.width(), max(self._unfolded_min_height, self._unfolded_height or 0))
        self.fold_button.setText("▸" if folded else "▾")
        self.state.panel(self.panel_name)["collapsed"] = folded
        self._save_timer.start()

    # ---- flags / opacity ----------------------------------------------------------------
    def _apply_flags(self, on_top: bool):
        flags = Qt.Tool | Qt.FramelessWindowHint
        if on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def _on_top_toggled(self, checked: bool):
        visible = self.isVisible()
        geo = self.geometry()
        self._apply_flags(checked)
        self.setGeometry(geo)
        if visible:
            self.show()
        self.state.panel(self.panel_name)["on_top"] = checked
        self._save_timer.start()

    def _on_opacity(self, value: int):
        self.setWindowOpacity(value / 100)
        self.state.panel(self.panel_name)["opacity"] = value / 100
        self._save_timer.start()

    # ---- geometry persistence ------------------------------------------------------------
    def restore_geometry(self):
        p = self.state.panel(self.panel_name)
        rect = QRect(int(p["x"]), int(p["y"]), int(p["w"]), int(p["h"]))
        self.setGeometry(_clamp_to_screens(rect, self.minimumSize()))
        self.setWindowOpacity(float(p.get("opacity", 1.0)))
        self.set_folded(bool(p.get("collapsed", False)))

    def reset_geometry(self):
        d = DEFAULT_PANELS[self.panel_name]
        self.set_folded(False)
        self.setGeometry(QRect(d["x"], d["y"], d["w"], d["h"]))
        self.opacity_slider.setValue(100)
        self.on_top_action.setChecked(True)

    def moveEvent(self, e):
        super().moveEvent(e)
        self._save_timer.start()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._save_timer.start()

    def _persist(self):
        g = self.geometry()
        h = self._unfolded_height if self.folded and self._unfolded_height else g.height()
        self.state.panel(self.panel_name).update({"x": g.x(), "y": g.y(), "w": g.width(), "h": h,
                                                  "collapsed": self.folded})
        self.state.save()

    # ---- title-bar drag -----------------------------------------------------------------------
    def eventFilter(self, obj, e):
        if obj is self.title_bar:
            if e.type() == QEvent.MouseButtonPress and e.button() == Qt.LeftButton:
                self._drag_origin = e.globalPosition().toPoint()
                self._drag_start_geo = self.geometry()
                return True
            if e.type() == QEvent.MouseMove and self._drag_origin is not None:
                delta = e.globalPosition().toPoint() - self._drag_origin
                self.move(self._drag_start_geo.topLeft() + delta)
                return True
            if e.type() == QEvent.MouseButtonRelease:
                self._drag_origin = None
                return True
            if e.type() == QEvent.MouseButtonDblClick and e.button() == Qt.LeftButton:
                self._drag_origin = None
                self.toggle_fold()          # "shade", like a window manager
                return True
        return super().eventFilter(obj, e)

    # ---- edge / corner resize ----------------------------------------------------------------
    def _edges_at(self, pos: QPoint):
        edges = set()
        r = self.rect()
        if pos.x() <= RESIZE_MARGIN: edges.add('l')
        if pos.x() >= r.right() - RESIZE_MARGIN: edges.add('r')
        if not self.folded:                 # a folded panel has a fixed height
            if pos.y() <= RESIZE_MARGIN: edges.add('t')
            if pos.y() >= r.bottom() - RESIZE_MARGIN: edges.add('b')
        return edges

    @staticmethod
    def _cursor_for(edges):
        if edges in ({'l', 't'}, {'r', 'b'}): return Qt.SizeFDiagCursor
        if edges in ({'r', 't'}, {'l', 'b'}): return Qt.SizeBDiagCursor
        if edges & {'l', 'r'}: return Qt.SizeHorCursor
        if edges & {'t', 'b'}: return Qt.SizeVerCursor
        return Qt.ArrowCursor

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            edges = self._edges_at(e.position().toPoint())
            if edges:
                self._resize_edges = edges
                self._drag_origin = e.globalPosition().toPoint()
                self._drag_start_geo = self.geometry()
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._resize_edges:
            delta = e.globalPosition().toPoint() - self._drag_origin
            g = QRect(self._drag_start_geo)
            if 'l' in self._resize_edges: g.setLeft(g.left() + delta.x())
            if 'r' in self._resize_edges: g.setRight(g.right() + delta.x())
            if 't' in self._resize_edges: g.setTop(g.top() + delta.y())
            if 'b' in self._resize_edges: g.setBottom(g.bottom() + delta.y())
            ms = self.minimumSize()
            if g.width() < ms.width():
                if 'l' in self._resize_edges: g.setLeft(g.right() - ms.width() + 1)
                else: g.setRight(g.left() + ms.width() - 1)
            if g.height() < ms.height():
                if 't' in self._resize_edges: g.setTop(g.bottom() - ms.height() + 1)
                else: g.setBottom(g.top() + ms.height() - 1)
            self.setGeometry(g)
            return
        self.setCursor(self._cursor_for(self._edges_at(e.position().toPoint())))
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._resize_edges = None
        self._drag_origin = None
        super().mouseReleaseEvent(e)

    def leaveEvent(self, e):
        self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(e)


def _clamp_to_screens(rect: QRect, min_size) -> QRect:
    '''Keep a saved geometry usable if the monitor layout changed.'''
    screens = QGuiApplication.screens()
    if not screens:
        return rect
    virtual = QRect()
    for s in screens:
        virtual = virtual.united(s.availableGeometry())
    rect = QRect(rect)
    rect.setWidth(max(min_size.width(), min(rect.width(), virtual.width())))
    rect.setHeight(max(min_size.height(), min(rect.height(), virtual.height())))
    if rect.right() > virtual.right(): rect.moveRight(virtual.right())
    if rect.bottom() > virtual.bottom(): rect.moveBottom(virtual.bottom())
    if rect.left() < virtual.left(): rect.moveLeft(virtual.left())
    if rect.top() < virtual.top(): rect.moveTop(virtual.top())
    return rect
