'''Application controller: owns the source image, crop, adjustments, the
processed output + draw plan, the Drawer, hotkeys and persisted state.
Panels only talk to this object.'''
import os

from PIL import Image, ImageGrab, UnidentifiedImageError
from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtWidgets import QFileDialog, QApplication

from core.actuator import ColorPicker, PencilTool
from core.audio import Audio
from core.calibration import CalibrationModel
from core.drawer import Drawer, IDLE, RUNNING
from core.hotkeys import HotkeyManager
from core.pipeline import NormRect, Adjustments, process, to_rgba
from core.plan import build_plan
from core.state import UiState

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff);;All files (*.*)"


class PixelerApp(QObject):
    source_changed = Signal(object)          # PIL image or None
    output_changed = Signal(object, list)    # processed 32x32 image (or None), steps
    crop_changed = Signal(object)            # NormRect
    adjustments_changed = Signal(object)     # Adjustments
    status = Signal(str, bool)               # message, is_error
    panels_toggled = Signal(bool)

    def __init__(self):
        super().__init__()
        self.state = UiState()
        self.state.load()
        self.calibration = CalibrationModel()
        self.calibration.load_config()

        self.color_picker = ColorPicker(self.calibration)
        self.pencil = PencilTool(self.calibration, self.color_picker)
        self.drawer = Drawer(self.pencil)
        self.drawer.start_delay = self.state.start_delay
        self.drawer.error.connect(lambda m: self.status.emit(m, True))
        self.drawer.finished.connect(self._on_finished)

        self.hotkeys = HotkeyManager(self.state.hotkeys)
        self.hotkeys.triggered.connect(self._on_hotkey)

        self.source = None
        self.crop = self.state.crop
        self.adjustments = self.state.adjustments
        self.output = None
        self.steps = []
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
            self._set_source(to_rgba(img), f"Loaded {os.path.basename(path)} ({img.width}x{img.height})")
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

    def _set_source(self, img, message: str):
        self.source = img
        self.source_changed.emit(img)
        self.status.emit(message, False)
        self.rebuild()

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
            self.steps = build_plan(self.output)
        self.drawer.set_steps(self.steps)
        self.output_changed.emit(self.output, self.steps)

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
