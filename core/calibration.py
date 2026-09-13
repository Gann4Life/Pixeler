import json
import os

from .audio import Audio

GRID = 32
CONFIG_FILENAME = 'config.json'


class CalibrationModel:
    '''Where the game's canvas and color picker are on screen (physical pixels).

    The canvas is a square `area = (x0, y0, size)` divided into GRID x GRID cells.
    `config.json` keeps the legacy `x`/`y` center lists (regenerated on save) so
    older tooling keeps working, and gains an `area` key.
    '''

    def __init__(self, filepath: str = CONFIG_FILENAME):
        self.filepath = filepath
        self.fps = 0
        self.area = None            # (x0, y0, size) floats, or None
        self.colorCord = [0, 0]
        self.inputCord = [0, 0]
        self.closeCord = [0, 0]

    # ---- grid -------------------------------------------------------------
    @property
    def cell(self) -> float:
        return self.area[2] / GRID if self.area else 0.0

    def cell_center(self, gx: int, gy: int) -> tuple:
        x0, y0, size = self.area
        c = size / GRID
        return (round(x0 + (gx + 0.5) * c), round(y0 + (gy + 0.5) * c))

    @property
    def x(self) -> list:
        return [self.cell_center(i, 0)[0] for i in range(GRID)] if self.area else []

    @property
    def y(self) -> list:
        return [self.cell_center(0, i)[1] for i in range(GRID)] if self.area else []

    @staticmethod
    def area_from_centers(xs: list, ys: list):
        '''Derive the square from legacy top-row / left-column center lists.'''
        if len(xs) != GRID or len(ys) != GRID:
            return None
        cell_x = (xs[-1] - xs[0]) / (GRID - 1)
        cell_y = (ys[-1] - ys[0]) / (GRID - 1)
        cell = (cell_x + cell_y) / 2
        if cell <= 0:
            return None
        return (xs[0] - cell / 2, ys[0] - cell / 2, cell * GRID)

    # ---- validity / timing ------------------------------------------------
    def is_config_valid(self) -> bool:
        return (self.area is not None and self.area[2] > 0 and
                list(self.colorCord) != [0, 0] and
                list(self.inputCord) != [0, 0] and
                list(self.closeCord) != [0, 0] and
                self.fps > 0)

    def get_frame_sleep_time(self) -> float:
        '''Sleep between inputs, slightly longer than one frame so the game registers them.'''
        fps = self.fps if self.fps > 0 else 60
        return (1 / fps) * 1.2

    # ---- persistence ------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "fps": self.fps,
            "area": list(self.area) if self.area else None,
            "colorCord": list(self.colorCord),
            "inputCord": list(self.inputCord),
            "closeCord": list(self.closeCord),
            "x": self.x,
            "y": self.y,
        }

    def from_dict(self, data: dict):
        self.fps = int(data.get("fps", 0) or 0)
        self.colorCord = list(data.get("colorCord", [0, 0]))
        self.inputCord = list(data.get("inputCord", [0, 0]))
        self.closeCord = list(data.get("closeCord", [0, 0]))
        area = data.get("area")
        if area and len(area) == 3 and area[2] > 0:
            self.area = tuple(float(v) for v in area)
        else:
            # Migration from the click-64-pixels format.
            self.area = self.area_from_centers(data.get("x", []), data.get("y", []))

    def safe_save(self) -> bool:
        '''Saves only if everything is set. Returns False (and plays the error sound) otherwise.'''
        if not self.is_config_valid():
            Audio.play_error()
            return False
        self.save_config()
        return True

    def save_config(self, filepath: str = None):
        filepath = filepath or self.filepath
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=4)
        print("Configuration saved to", filepath)

    def load_config(self, filepath: str = None) -> bool:
        filepath = filepath or self.filepath
        if not os.path.exists(filepath):
            print("No configuration file found. Please run calibration.")
            return False
        try:
            with open(filepath, 'r') as f:
                self.from_dict(json.load(f))
            print(f"Configuration loaded from {filepath}.")
            return True
        except json.JSONDecodeError:
            print("Error decoding JSON from the configuration file.")
            Audio.play_error()
            return False
