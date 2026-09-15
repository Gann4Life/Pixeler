'''Per-machine UI state (ui_state.json, gitignored): panel geometry and opacity,
crop, adjustments, hotkey bindings, the output preview toggle and the last open artwork.'''
import json
import os

from .actuator import PenSettings
from .order import DEFAULT_METHOD, DEFAULT_COLOR_ORDER, method_keys, color_order_keys
from .pipeline import NormRect, Adjustments

STATE_FILENAME = 'ui_state.json'
SPEED_MIN, SPEED_MAX = 0.25, 4.0

DEFAULT_PANELS = {
    "input":  {"x": 40,  "y": 60, "w": 360, "h": 420, "opacity": 1.0, "on_top": True},
    "output": {"x": 420, "y": 60, "w": 520, "h": 420, "opacity": 1.0, "on_top": True},
    "status": {"x": 40,  "y": 500, "w": 400, "h": 96, "opacity": 0.9, "on_top": True},
    # starts folded: an empty list is not worth 480 px next to the game
    "artworks": {"x": 960, "y": 60, "w": 300, "h": 480, "opacity": 1.0, "on_top": True, "collapsed": True},
}


class UiState:
    def __init__(self, filepath: str = STATE_FILENAME):
        self.filepath = filepath
        self.panels = {k: dict(v) for k, v in DEFAULT_PANELS.items()}
        self.crop = NormRect()
        self.adjustments = Adjustments()
        self.hotkeys = {}
        self.output_shows_final = True
        self.start_delay = 1.5       # seconds between "all keys released" and the first click
        self.draw_method = DEFAULT_METHOD
        self.draw_seed = 0           # for the randomized draw orders (maze, scatter, random colors)
        self.color_order = DEFAULT_COLOR_ORDER
        self.speed = 1.0             # multiplier on the per-frame wait (1.0 = as FPS dictates)
        self.pen = PenSettings()
        self.last_image_dir = ""
        self.remember_session = True   # reopen last_artwork on startup
        self.last_artwork = ""         # name of the artwork that was open when we quit

    def panel(self, name: str) -> dict:
        return self.panels.setdefault(name, dict(DEFAULT_PANELS.get(name, DEFAULT_PANELS["input"])))

    def to_dict(self) -> dict:
        return {
            "panels": self.panels,
            "crop": self.crop.to_dict(),
            "adjustments": self.adjustments.to_dict(),
            "hotkeys": self.hotkeys,
            "output_shows_final": self.output_shows_final,
            "start_delay": self.start_delay,
            "draw_method": self.draw_method,
            "draw_seed": self.draw_seed,
            "color_order": self.color_order,
            "speed": self.speed,
            "pen": self.pen.to_dict(),
            "last_image_dir": self.last_image_dir,
            "remember_session": self.remember_session,
            "last_artwork": self.last_artwork,
        }

    def from_dict(self, d: dict):
        for name, p in (d.get("panels") or {}).items():
            self.panel(name).update({k: v for k, v in p.items() if k != "visible"})
        self.crop = NormRect.from_dict(d.get("crop"))
        self.adjustments = Adjustments.from_dict(d.get("adjustments"))
        self.hotkeys = dict(d.get("hotkeys") or {})
        self.output_shows_final = bool(d.get("output_shows_final", True))
        try:
            self.start_delay = max(0.0, float(d.get("start_delay", 1.5)))
        except (TypeError, ValueError):
            self.start_delay = 1.5
        self.draw_method = d.get("draw_method") if d.get("draw_method") in method_keys() else DEFAULT_METHOD
        self.color_order = d.get("color_order") if d.get("color_order") in color_order_keys() else DEFAULT_COLOR_ORDER
        try:
            self.draw_seed = int(d.get("draw_seed", 0))
        except (TypeError, ValueError):
            self.draw_seed = 0
        try:
            self.speed = min(SPEED_MAX, max(SPEED_MIN, float(d.get("speed", 1.0))))
        except (TypeError, ValueError):
            self.speed = 1.0
        self.pen = PenSettings.from_dict(d.get("pen"))
        self.last_image_dir = d.get("last_image_dir", "") or ""
        self.remember_session = bool(d.get("remember_session", True))
        self.last_artwork = str(d.get("last_artwork") or "")

    def load(self) -> bool:
        if not os.path.exists(self.filepath):
            return False
        try:
            with open(self.filepath, 'r') as f:
                self.from_dict(json.load(f))
            return True
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as e:
            print(f"[state] could not read {self.filepath}: {e}")
            return False

    def save(self):
        try:
            tmp = self.filepath + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(self.to_dict(), f, indent=2)
            os.replace(tmp, self.filepath)
        except OSError as e:
            print(f"[state] could not write {self.filepath}: {e}")
