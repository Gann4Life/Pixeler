'''Artworks panel: the saved artworks (core/artwork.py) as a list, newest first, with the
selected one's 32x32 preview. Load / Save / Rename (F2) / Delete (Del); double-click loads.'''
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QPushButton, QListWidget, QListWidgetItem, QLabel,
                               QAbstractItemView, QInputDialog, QMessageBox)

from core import artwork as artworks
from core.drawer import RUNNING
from .app import PixelerApp
from .floating_panel import FloatingPanel
from .output_panel import PreviewWidget


class ArtworksPanel(FloatingPanel):
    def __init__(self, app: PixelerApp):
        super().__init__("artworks", "Artworks", app.state, min_size=(220, 260))
        self.app = app
        self._syncing = False
        self._running = False

        # ---- buttons
        row = QHBoxLayout()
        row.setSpacing(4)
        self.load_button = QPushButton("Load")
        self.load_button.setToolTip("Open the selected artwork: image, crop, zoom and output settings  (double-click)")
        self.save_button = QPushButton("Save")
        self.save_button.setToolTip("Save the current image, crop, zoom and output settings as an artwork")
        self.rename_button = QPushButton("Rename")
        self.rename_button.setToolTip("Rename the selected artwork  (F2)")
        self.delete_button = QPushButton("Delete")
        self.delete_button.setToolTip("Delete the selected artwork  (Del)")
        for b in (self.load_button, self.save_button, self.rename_button, self.delete_button):
            row.addWidget(b)
        self.body.addLayout(row)

        # ---- list
        self.list = QListWidget()
        self.list.setEditTriggers(QAbstractItemView.EditKeyPressed)   # F2 = inline rename
        self.list.setToolTip("Saved artworks, newest first. Double-click to load, F2 to rename, Del to delete.")
        self.body.addWidget(self.list, 3)
        QShortcut(QKeySequence.Delete, self.list, activated=self._delete, context=Qt.WidgetShortcut)

        # ---- preview of the selected artwork
        self.preview = PreviewWidget()
        self.preview.setToolTip("Output of the selected artwork, as it was when saved")
        self.body.addWidget(self.preview, 2)
        self.meta = QLabel("—")
        self.meta.setStyleSheet("color: #a0a3a8; font-size: 11px;")
        self.meta.setWordWrap(True)
        self.body.addWidget(self.meta)

        # ---- wiring
        self.load_button.clicked.connect(self._load)
        self.save_button.clicked.connect(self._save)
        self.rename_button.clicked.connect(self._rename)
        self.delete_button.clicked.connect(self._delete)
        self.list.itemDoubleClicked.connect(lambda _: self._load())
        self.list.currentItemChanged.connect(self._on_current)
        self.list.itemChanged.connect(self._on_item_edited)
        app.artworks_changed.connect(self.refresh)
        app.artwork_changed.connect(self._on_artwork)
        app.source_changed.connect(lambda _: self._update_buttons())
        app.drawer.state_changed.connect(self._on_state)
        self.refresh()

    # ---- list --------------------------------------------------------------------------------------
    def refresh(self):
        current = self.selected_name()
        self._syncing = True
        self.list.clear()
        for info in artworks.list_artworks():
            item = QListWidgetItem(info.name)
            item.setData(Qt.UserRole, info.name)
            item.setToolTip(self._describe(info))
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            self.list.addItem(item)
        self._syncing = False
        self._mark_open()
        self._select(current or self.app.artwork)
        self._update_buttons()

    @staticmethod
    def _describe(info: artworks.ArtworkInfo) -> str:
        w, h = info.source_size
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(info.saved_at))
        return f"saved {when}  ·  {w}×{h} source  ·  {info.colors} colors  ·  {info.steps} steps"

    def selected_name(self):
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _select(self, name):
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == name:
                self.list.setCurrentRow(i)
                return
        self._on_current(self.list.currentItem(), None)

    def _mark_open(self):
        '''The open artwork is bold. setFont fires itemChanged, so this must not look like an edit.'''
        was = self._syncing
        self._syncing = True
        for i in range(self.list.count()):
            item = self.list.item(i)
            font = QFont(item.font())
            font.setBold(item.data(Qt.UserRole) == self.app.artwork)
            item.setFont(font)
        self._syncing = was

    def _on_current(self, item, _previous=None):
        name = item.data(Qt.UserRole) if item else None
        self.preview.set_image(artworks.load_preview(name) if name else None)
        if item:
            self.meta.setText(item.toolTip())
        else:
            self.meta.setText("No artworks saved yet." if not self.list.count() else "—")
        self._update_buttons()

    def _on_artwork(self, name):
        self._mark_open()
        if name:
            self._select(name)

    def _update_buttons(self):
        has = self.list.currentItem() is not None
        self.load_button.setEnabled(has and not self._running)
        self.save_button.setEnabled(self.app.source is not None)
        self.rename_button.setEnabled(has)
        self.delete_button.setEnabled(has)

    def _on_state(self, state: str):
        self._running = state == RUNNING
        self._update_buttons()

    # ---- actions -------------------------------------------------------------------------------------
    def _load(self):
        name = self.selected_name()
        if name and not self._running:
            self.app.load_artwork(name)

    def _save(self) -> bool:
        '''Ask for a name and save. Returns True once the artwork is on disk.'''
        if self.app.source is None:
            return False
        dlg = QInputDialog(self._dialog_parent())
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowStaysOnTopHint)
        dlg.setWindowTitle("Save artwork")
        dlg.setLabelText("Name:")
        dlg.setInputMode(QInputDialog.TextInput)
        dlg.setTextValue(self.app.artwork or self.app.source_name or "Untitled")
        if dlg.exec() != QInputDialog.Accepted:
            return False
        try:
            name = artworks.safe_name(dlg.textValue())
        except ValueError as e:
            self.app.status.emit(str(e), True)
            return False
        if name != self.app.artwork and artworks.artwork_exists(name):
            if self._ask(f"Replace the artwork '{name}'?") != QMessageBox.Yes:
                return False
        return self.app.save_artwork(name)

    def confirm_close(self) -> bool:
        '''Quit guard: offers to save unsaved work. Returns False to keep the app open.'''
        if not self.app.is_dirty():
            return True
        if self.app.artwork:
            question = f"Save the changes to '{self.app.artwork}' before quitting?"
        else:
            question = "The current image was never saved as an artwork. Save it before quitting?"
        box = QMessageBox(QMessageBox.Question, "Pixeler", question,
                          QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, self._dialog_parent())
        box.setWindowFlags(box.windowFlags() | Qt.WindowStaysOnTopHint)
        box.setDefaultButton(QMessageBox.Save)
        answer = box.exec()
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Discard:
            return True
        if self.app.artwork:
            return self.app.save_artwork(self.app.artwork)
        return self._save()

    def _rename(self):
        item = self.list.currentItem()
        if item:
            self.list.editItem(item)

    def _on_item_edited(self, item: QListWidgetItem):
        if self._syncing:
            return
        old, new = item.data(Qt.UserRole), item.text()
        try:
            new = artworks.safe_name(new)
        except ValueError as e:
            self.app.status.emit(str(e), True)
            new = None
        self._syncing = True           # the rename refreshes and re-bolds the list: not edits
        try:
            ok = bool(new) and new != old and self.app.rename_artwork(old, new)
            if not ok:
                item.setText(old)      # revert; the folder did not change
        finally:
            self._syncing = False
        if not ok:
            return
        # rename_artwork emitted artworks_changed -> refresh() rebuilt the list; reselect under the new name
        QTimer.singleShot(0, lambda: self._select(new))

    def _delete(self):
        name = self.selected_name()
        if not name:
            return
        if self._ask(f"Delete the artwork '{name}'?\nThis cannot be undone.") != QMessageBox.Yes:
            return
        self.app.delete_artwork(name)

    def _dialog_parent(self):
        return self if self.isVisible() else None     # a hidden panel would swallow the dialog

    def _ask(self, question: str):
        box = QMessageBox(QMessageBox.Question, "Pixeler", question, QMessageBox.Yes | QMessageBox.No,
                          self._dialog_parent())
        box.setWindowFlags(box.windowFlags() | Qt.WindowStaysOnTopHint)
        box.setDefaultButton(QMessageBox.No)
        return box.exec()

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()
