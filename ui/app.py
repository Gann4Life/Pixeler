'''Application controller: owns the source image, crop, adjustments, the
processed output + draw plan, the Drawer, hotkeys and persisted state.
Panels only talk to this object. Also the open artwork (core/artwork.py): what is loaded,
cropped and tuned right now, saved and reopened as one unit.'''
import os
import random

from PIL import Image, ImageGrab, UnidentifiedImageError
from PySide6.QtCore import QObject, QTimer, Signal, Qt
from PySide6.QtWidgets import QFileDialog, QApplication

from core import artwork as artworks
from core.actuator import ColorPicker, PencilTool, PenSettings, tune_autoit
from core.audio import Audio
from core.calibration import CalibrationModel
from core.drawer import Drawer, IDLE, RUNNING
from core.hotkeys import HotkeyManager
from core.order import method_keys, color_order_keys
from core.pipeline import NormRect, Adjustments, process, to_rgba
from core.plan import build_plan, color_boundaries
from core.state import UiState, SPEED_MIN, SPEED_MAX

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff);;All files (*.*)"


class PixelerApp(QObject):
    source_changed = Signal(object)          # PIL image or None
    output_changed = Signal(object, list)    # processed 32x32 image (or None), steps
    crop_changed = Signal(object)            # NormRect
    adjustments_changed = Signal(object)     # Adjustments
    status = Signal(str, bool)               # message, is_error
    panels_toggled = Signal(bool)
    scrubbing = Signal(bool)                 # True while the timeline is being click-dragged
    draw_method_changed = Signal(str, int)   # method key, seed
    color_order_changed = Signal(str)
    speed_changed = Signal(float)
    pen_changed = Signal(object)             # PenSettings
    artwork_changed = Signal(object)         # name of the open artwork, or None (unsaved image)
    artworks_changed = Signal()              # the artworks folder changed: lists must refresh
    view_restored = Signal(object)           # Input zoom/pan from a loaded artwork

    def __init__(self):
        super().__init__()
        self.state = UiState()
        self.state.load()
        self.calibration = CalibrationModel()
        self.calibration.load_config()
        self.calibration.speed = self.state.speed

        self.color_picker = ColorPicker(self.calibration)
        self.pencil = PencilTool(self.calibration, self.color_picker, self.state.pen)
        tune_autoit(self.state.pen.click_hold)   # AutoIt's 10+10 ms per click dwarfs a frame
        self.drawer = Drawer(self.pencil)
        self.drawer.start_delay = self.state.start_delay
        self.drawer.error.connect(lambda m: self.status.emit(m, True))
        self.drawer.finished.connect(self._on_finished)

        self.hotkeys = HotkeyManager(self.state.hotkeys)
        self.hotkeys.triggered.connect(self._on_hotkey)
        self._speed_save = QTimer(self, singleShot=True, interval=400)
        self._speed_save.timeout.connect(self.state.save)

        self.source = None
        self.crop = self.state.crop
        self.adjustments = self.state.adjustments
        self.output = None
        self.steps = []
        self.draw_method = self.state.draw_method
        self.draw_seed = self.state.draw_seed
        self.color_order = self.state.color_order
        self.artwork = None  # name of the open artwork; None once a new image is loaded
        self.source_name = ""
        self._clean = None   # (source object, artwork dict) as of the last save/load; None = never saved
        self.view = artworks.default_view()   # mirror of the Input zoom/pan (never persisted per machine)
        self.panels = []     # set by __main__

    # ---- lifecycle ---------------------------------------------------------------------------
    def start(self):
        self.hotkeys.start()

    def shutdown(self):
        self.drawer.stop()
        self.hotkeys.stop()
        self.state.hotkeys = dict(self.hotkeys.bindings)
        self.state.save()

    # ---- image loading (error handling carried over from the old PixelExtractor) -----------
    def load_file(self, path: str = None):
        if path is None:
            start_dir = self.state.last_image_dir or os.getcwd()
            path, _ = QFileDialog.getOpenFileName(None, "Load image", start_dir, IMAGE_FILTER)
            if not path:
                return
        try:
            img = Image.open(path)
            img.load()
            self._set_source(to_rgba(img), f"Loaded {os.path.basename(path)} ({img.width}x{img.height})",
                             source_name=os.path.splitext(os.path.basename(path))[0])
            self.state.last_image_dir = os.path.dirname(path)
            self.state.save()
        except UnidentifiedImageError:
            self._error("Unsupported file format.")
        except PermissionError:
            self._error("Not enough permissions to read that file.")
        except (OSError, ValueError) as e:
            self._error(f"Could not open image: {e}")

    def load_clipboard(self):
        try:
            content = ImageGrab.grabclipboard()
        except Exception as e:  # pillow raises odd types on empty/foreign clipboards
            self._error(f"Could not read the clipboard: {e}")
            return
        if isinstance(content, list):
            paths = [p for p in content if os.path.isfile(p)]
            if not paths:
                self._error("Clipboard has no usable file.")
                return
            self.load_file(paths[0])
            return
        if content is None:
            self._error("Please copy an image to your clipboard first.")
            return
        try:
            self._set_source(to_rgba(content), f"Loaded clipboard image ({content.width}x{content.height})")
        except (OSError, ValueError) as e:
            self._error(f"Clipboard image is not usable: {e}")

    def _set_source(self, img, message: str, artwork: str = None, source_name: str = ""):
        self.source = img
        self.source_name = artwork or source_name   # suggested artwork name on Save
        self.artwork = artwork                # a fresh image is not the saved artwork any more
        self._clean = None
        self.state.last_artwork = artwork or ""
        self.source_changed.emit(img)
        self.artwork_changed.emit(artwork)
        self.status.emit(message, False)
        self.rebuild()

    # ---- artworks -------------------------------------------------------------------------------
    def set_view(self, view: dict):
        '''The Input panel reports its zoom/pan here so it can be saved with the artwork.'''
        self.view = dict(view)

    def _current_artwork(self) -> artworks.Artwork:
        return artworks.Artwork(crop=self.crop, adjustments=self.adjustments, draw_method=self.draw_method,
                                draw_seed=self.draw_seed, color_order=self.color_order, view=dict(self.view))

    def _snapshot(self) -> dict:
        '''What counts as a change: everything but the view (zooming is not editing).'''
        return {k: v for k, v in self._current_artwork().to_dict().items() if k != "view"}

    def _mark_clean(self):
        self._clean = (self.source, self._snapshot())

    def is_dirty(self) -> bool:
        '''True when quitting would lose something: an image never saved as an artwork, or an open
        artwork whose crop / adjustments / orders changed since it was saved or loaded.'''
        if self.source is None:
            return False
        if self.artwork is None or self._clean is None:
            return True
        source, snapshot = self._clean
        return source is not self.source or snapshot != self._snapshot()

    def save_artwork(self, name: str) -> bool:
        if self.source is None:
            self._error("Load an image first.")
            return False
        try:
            name = artworks.safe_name(name)
            art = self._current_artwork()
            artworks.save_artwork(name, self.source, self.output, art,
                                  colors=len(color_boundaries(self.steps)), steps=len(self.steps))
        except (OSError, ValueError) as e:
            self._error(f"Could not save the artwork: {e}")
            return False
        self.artwork = name
        self.state.last_artwork = name
        self._mark_clean()
        self.artwork_changed.emit(name)
        self.artworks_changed.emit()
        self.status.emit(f"Saved artwork {name}.", False)
        self.state.save()
        return True

    def load_artwork(self, name: str, quiet: bool = False) -> bool:
        '''Replaces image, crop, adjustments, draw/color order and the Input view in one go.
        `quiet` (startup) turns a missing folder into a silent no-op instead of an error.'''
        if self.drawer.state == RUNNING:
            self._error("Stop the drawing first.")
            return False
        try:
            img, art = artworks.load_artwork(name)
        except (OSError, ValueError) as e:
            if quiet:
                self.state.last_artwork = ""
                return False
            self._error(f"Could not open the artwork: {e}")
            return False
        self.stop()
        self.crop = self.state.crop = art.crop.clamped()
        self.adjustments = self.state.adjustments = art.adjustments
        self.draw_method = self.state.draw_method = art.draw_method
        self.draw_seed = self.state.draw_seed = art.draw_seed
        self.color_order = self.state.color_order = art.color_order
        self.crop_changed.emit(self.crop)
        self.adjustments_changed.emit(self.adjustments)
        self.draw_method_changed.emit(self.draw_method, self.draw_seed)
        self.color_order_changed.emit(self.color_order)
        self._set_source(img, f"Loaded artwork {name} ({img.width}x{img.height})", artwork=name)
        self.view_restored.emit(art.view)   # after _set_source: a new image resets the editor's view
        self._mark_clean()
        self.state.save()
        return True

    def rename_artwork(self, old: str, new: str) -> bool:
        try:
            new = artworks.rename_artwork(old, new)
        except (OSError, ValueError) as e:
            self._error(f"Could not rename: {e}")
            return False
        if self.artwork == old:
            self.artwork = new
            self.state.last_artwork = new
            self.artwork_changed.emit(new)
            self.state.save()
        self.artworks_changed.emit()
        return True

    def delete_artwork(self, name: str) -> bool:
        try:
            artworks.delete_artwork(name)
        except (OSError, ValueError) as e:
            self._error(f"Could not delete: {e}")
            return False
        if self.artwork == name:                 # the image stays loaded, it is just unsaved now
            self.artwork = None
            self.state.last_artwork = ""
            self.artwork_changed.emit(None)
            self.state.save()
        self.artworks_changed.emit()
        self.status.emit(f"Deleted artwork {name}.", False)
        return True

    def set_remember_session(self, remember: bool):
        self.state.remember_session = bool(remember)
        self.state.save()

    # ---- crop / adjustments ----------------------------------------------------------------
    def set_crop(self, crop: NormRect):
        self.crop = crop.clamped()
        self.state.crop = self.crop
        self.crop_changed.emit(self.crop)
        self.rebuild()
        self.state.save()

    def reset_crop(self):
        self.set_crop(NormRect())

    def set_adjustments(self, adj: Adjustments):
        self.adjustments = adj
        self.state.adjustments = adj
        self.adjustments_changed.emit(adj)
        self.rebuild()
        self.state.save()

    def rebuild(self):
        '''Re-run the pipeline and the plan. Ignored while a draw is running.'''
        if self.drawer.state == RUNNING:
            return
        if self.source is None:
            self.output, self.steps = None, []
        else:
            self.output = process(self.source, self.crop, self.adjustments)
            self.steps = build_plan(self.output, self.draw_method, self.draw_seed, self.color_order)
        self.drawer.set_steps(self.steps)
        self.output_changed.emit(self.output, self.steps)

    # ---- draw order ---------------------------------------------------------------------------
    def set_draw_method(self, method: str, seed: int = None):
        if method not in method_keys():
            return
        self.draw_method = method
        if seed is not None:
            self.draw_seed = int(seed)
        self.state.draw_method, self.state.draw_seed = self.draw_method, self.draw_seed
        self.draw_method_changed.emit(self.draw_method, self.draw_seed)
        self.rebuild()
        self.state.save()

    def set_speed(self, speed: float):
        '''Live: the pencil reads the frame wait on every input, so this applies mid-draw.
        The save is debounced — dragging the slider would otherwise rewrite ui_state.json a
        few hundred times, on the UI thread, while the worker is chasing millisecond frames.'''
        self.state.speed = min(SPEED_MAX, max(SPEED_MIN, float(speed)))
        self.calibration.speed = self.state.speed
        self.speed_changed.emit(self.state.speed)
        self._speed_save.start(400)

    def set_pen(self, pen: PenSettings):
        self.state.pen = pen
        self.pencil.pen = pen
        tune_autoit(pen.click_hold)
        self.pen_changed.emit(pen)
        self.state.save()

    def set_color_order(self, order: str):
        if order not in color_order_keys():
            return
        self.color_order = self.state.color_order = order
        self.color_order_changed.emit(order)
        self.rebuild()
        self.state.save()

    def reroll_seed(self):
        '''New random seed for the randomized orders (maze, scatter, random colors).'''
        self.set_draw_method(self.draw_method, random.randrange(1, 1_000_000))

    # ---- transport ----------------------------------------------------------------------------
    def play_pause(self):
        if self.drawer.state == RUNNING:
            self.drawer.pause()
            self.status.emit("Paused.", False)
            return
        if self.source is None:
            self._error("Load an image first.")
            return
        if not self.calibration.is_config_valid():
            self._error("Calibrate the screen first (⚙ → Calibrate).")
            return
        self.drawer.play()

    def stop(self):
        if self.drawer.state != IDLE:
            self.drawer.stop()
            self.status.emit("Stopped.", False)

    def seek(self, index: int):
        self.drawer.seek(index)

    def set_start_delay(self, seconds: float):
        self.state.start_delay = max(0.0, float(seconds))
        self.drawer.start_delay = self.state.start_delay
        self.state.save()

    def _on_finished(self, completed: bool):
        self.status.emit("Drawing complete!" if completed else "Stopped.", False)

    # ---- panels / hotkeys -----------------------------------------------------------------------
    def toggle_panels(self):
        any_visible = any(p.isVisible() for p in self.panels)
        for p in self.panels:
            p.setVisible(not any_visible)
        self.panels_toggled.emit(not any_visible)

    def _on_hotkey(self, action: str):
        {
            "play_pause": self.play_pause,
            "stop": self.stop,
            "load_file": self.load_file,
            "load_clipboard": self.load_clipboard,
            "reset_crop": self.reset_crop,
            "toggle_panels": self.toggle_panels,
        }.get(action, lambda: None)()

    def save_hotkeys(self):
        self.state.hotkeys = dict(self.hotkeys.bindings)
        self.state.save()

    def _error(self, message: str):
        Audio.play_error()
        self.status.emit(message, True)
