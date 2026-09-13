'''Per-machine UI state (ui_state.json, gitignored): panel geometry and opacity,
crop, adjustments, hotkey bindings and the output preview toggle.'''
import json
import os

from .pipeline import NormRect, Adjustments

STATE_FILENAME = 'ui_state.json'

DEFAULT_PANELS = {
    "input":  {"x": 40,  "y": 60, "w": 360, "h": 420, "opacity": 1.0, "on_top": True},
    "output": {"x": 420, "y": 60, "w": 520, "h": 420, "opacity": 1.0, "on_top": True},
    "status": {"x": 40,  "y": 500, "w": 400, "h": 96, "opacity": 0.9, "on_top": True},
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
        self.last_image_dir = ""

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
            "last_image_dir": self.last_image_dir,
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
        self.last_image_dir = d.get("last_image_dir", "") or ""

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
