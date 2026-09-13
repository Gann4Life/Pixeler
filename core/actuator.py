import time
from dataclasses import dataclass, asdict

import autoit
import keyboard

from .calibration import CalibrationModel

GAME_WINDOW = "Roblox"     # window title prefix (autoit matches the start of the title)


def focus_game(settle: float = 0.15) -> bool:
    '''Bring the game to the foreground. Play from the UI focuses a Pixeler panel, and the
    first click into an unfocused Roblox only activates the window — it never reaches the
    color button. Returns False if no game window was found.'''
    try:
        if autoit.win_exists(GAME_WINDOW):
            if not autoit.win_active(GAME_WINDOW):
                autoit.win_activate(GAME_WINDOW)
                time.sleep(settle)
            return True
    except Exception as e:   # noqa: BLE001 - autoit raises plain exceptions
        print(f"[focus] {e}")
    return False


def _settle_click(x, y, sleep):
    '''Roblox needs a little jitter before it registers a click at a new spot.'''
    autoit.mouse_move(x, y, 0)
    time.sleep(sleep)
    autoit.mouse_move(x + 1, y + 1, 0)
    time.sleep(0.005)
    autoit.mouse_move(x - 1, y - 1, 0)
    time.sleep(sleep)
    autoit.mouse_click()


def _wait_modifiers_released(timeout: float = 3.0):
    '''If Play was triggered by a Ctrl+Shift hotkey the keys may still be held; typing the
    hex code then would send shifted characters ("#f8c8d8" -> "#F(C(D(").'''
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not any(keyboard.is_pressed(k) for k in ("ctrl", "shift", "alt", "windows")):
            return
        time.sleep(0.02)


class ColorPicker:
    def __init__(self, settings: CalibrationModel):
        self.settings = settings
        self.current_color = ""

    def reset(self):
        '''Forget the last picked color so the next draw re-picks it (after a scrub).'''
        self.current_color = ""

    def pick(self, color: str) -> None:
        if self.current_color == color:
            return
        self.open()
        self.current_color = color
        self.write_color(color)
        self.close()

    def open(self) -> None:
        x, y = self.settings.colorCord
        _settle_click(x, y, self.settings.get_frame_sleep_time())

    def write_color(self, color: str) -> None:
        x, y = self.settings.inputCord
        _settle_click(x, y, self.settings.get_frame_sleep_time())
        _wait_modifiers_released()
        print(f"[color] typing {color}")
        # A small per-character delay keeps Roblox from dropping characters.
        keyboard.write(color, delay=0.01)

    def close(self) -> None:
        x, y = self.settings.closeCord
        _settle_click(x, y, self.settings.get_frame_sleep_time())


@dataclass
class PenSettings:
    '''How the pencil moves between cells. Persisted in ui_state.json.'''
    hold_stroke: bool = True      # keep the button held while the next cell touches the current one
    pen_delay: float = 0.0        # extra wait after every pen down / pen up (seconds)
    color_delay: float = 0.10     # extra wait after every color change (seconds)
    interpolate: bool = False     # glide the cursor between cells instead of teleporting
    glide: int = 5                # autoit move speed when interpolating: 1 = fastest … 100 = slowest

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d) -> "PenSettings":
        base = cls()
        if not isinstance(d, dict):
            return base
        try:
            return cls(
                hold_stroke=bool(d.get("hold_stroke", base.hold_stroke)),
                pen_delay=min(2.0, max(0.0, float(d.get("pen_delay", base.pen_delay)))),
                color_delay=min(5.0, max(0.0, float(d.get("color_delay", base.color_delay)))),
                interpolate=bool(d.get("interpolate", base.interpolate)),
                glide=min(100, max(1, int(d.get("glide", base.glide)))),
            )
        except (TypeError, ValueError):
            return base


def adjacent(a, b) -> bool:
    '''True when grid cells a and b touch (8 directions).'''
    return a is not None and b is not None and max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 1


class PencilTool:
    '''Executes DrawSteps. With `pen.hold_stroke` the button stays held while consecutive
    steps are neighbours (one frame per cell); a jump or a color change lifts the pen.
    Without it every cell is clicked the legacy way.'''

    def __init__(self, settings: CalibrationModel, color_picker: ColorPicker, pen: PenSettings = None):
        self.settings = settings
        self.color_picker = color_picker
        self.pen = pen or PenSettings()
        self._down = False
        self._last = None      # grid cell of the last step drawn in the current stroke

    # ---- pen state ---------------------------------------------------------
    def pen_down(self):
        if not self._down:
            autoit.mouse_down("left")
            self._down = True
            time.sleep(self.pen.pen_delay)

    def pen_up(self):
        '''Safe to call any time (pause, stop, errors): lifts the button if it is held.'''
        if self._down:
            autoit.mouse_up("left")
            self._down = False
            time.sleep(self.pen.pen_delay)
        self._last = None

    def reset(self):
        self.pen_up()
        self.color_picker.reset()

    def _move(self, x, y):
        '''Glide (blocking, autoit paces it) or teleport. Either way the caller budgets one frame.'''
        autoit.mouse_move(x, y, self.pen.glide if self.pen.interpolate else 0)

    def _wait_frame(self, t0: float):
        '''Sleep whatever is left of one frame since t0, so a cell costs the same whether the
        cursor glided or teleported and whether the button is held or clicked.'''
        left = self.settings.get_frame_sleep_time() - (time.perf_counter() - t0)
        if left > 0:
            time.sleep(left)

    @staticmethod
    def _jitter(x, y):
        # This many inputs is because roblox sucks: it registers presses better with motion.
        autoit.mouse_move(x + 1, y + 1, 0)
        time.sleep(0.001)
        autoit.mouse_move(x - 1, y - 1, 0)
        time.sleep(0.001)
        autoit.mouse_move(x, y, 0)

    # ---- legacy: click every cell (one frame per cell) --------------------
    def draw_at(self, x, y):
        t0 = time.perf_counter()
        self._move(x, y)
        autoit.mouse_click()
        autoit.mouse_move(x + 1, y + 1, 0)
        time.sleep(0.001)
        autoit.mouse_click()
        autoit.mouse_move(x - 1, y - 1, 0)
        time.sleep(0.001)
        autoit.mouse_click()
        autoit.mouse_move(x, y, 0)
        self._wait_frame(t0)
        autoit.mouse_click()

    def draw_color_at(self, color: str, x, y):
        self.color_picker.pick(color)
        self.draw_at(x, y)

    # ---- the seam the Drawer calls ---------------------------------------
    def draw_step(self, step) -> None:
        '''One cell = one frame in every mode; hold on/off and glide/teleport only change what
        happens inside that frame. Only the configured pen/color delays add time.'''
        x, y = self.settings.cell_center(step.gx, step.gy)
        if step.color != self.color_picker.current_color:
            self.pen_up()
            self.color_picker.pick(step.color)
            time.sleep(self.pen.color_delay)
        if not self.pen.hold_stroke:
            self.draw_at(x, y)
            return
        cell = (step.gx, step.gy)
        if self._down and adjacent(self._last, cell):
            t0 = time.perf_counter()
            self._move(x, y)                      # stroke continues: the game paints the cell on the next frame
            self._wait_frame(t0)
        else:
            self.pen_up()                         # too far: hop with the pen up, then start a new stroke
            t0 = time.perf_counter()
            self._move(x, y)
            self._jitter(x, y)
            self._wait_frame(t0)
            self.pen_down()                       # pressed at the end of the frame, where a legacy click lands
        self._last = cell

    @staticmethod
    def move_to(x, y):
        autoit.mouse_move(int(x), int(y), 0)
