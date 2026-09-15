import contextlib
import time
from dataclasses import dataclass, asdict

import autoit
import keyboard

from .calibration import CalibrationModel

GAME_WINDOW = "Roblox"     # window title prefix (autoit matches the start of the title)

# Measured with scratchpad/bench_timing.py. These are the floor: work that has to happen
# inside a cell's frame budget no matter how high Speed goes.
MOVE_COST = 0.0002       # autoit.mouse_move(..., 0): ~0.11 ms, independent of distance
PRESS_COST = 0.0004      # mouse_down or mouse_up: ~0.17 ms for the pair
CLICK_BASE = 0.0002      # mouse_click() once AutoIt's own delays are off: ~0.20 ms
GLIDE_SLICE = 0.001      # smallest slice we can actually pace (Drawer holds timeBeginPeriod(1))


def tune_autoit(click_hold_ms: int = 1) -> None:
    '''AutoIt ships with MouseClickDelay=10 and MouseClickDownDelay=10, so every
    `mouse_click()` blocks for ~20 ms inside the DLL — more than twice a 120 FPS frame
    budget, which pinned the click-per-cell mode below any Speed setting.

    We pace cells ourselves, so the trailing delay goes to 0. The down->up hold is kept
    short but non-zero: that is the part Roblox needs to see a press at all.'''
    with contextlib.suppress(Exception):
        autoit.auto_it_set_option("MouseClickDelay", 0)
        autoit.auto_it_set_option("MouseClickDownDelay", max(0, int(click_hold_ms)))


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
    time.sleep(min(0.005, sleep))     # never let the nudge outweigh the frame itself
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
    interpolate: bool = False     # walk the cursor between cells instead of teleporting
    glide_steps: int = 4          # hops per move when interpolating; spread across the frame
    click_hold: int = 1           # ms the button stays down inside a click (AutoIt MouseClickDownDelay)

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def click_cost(self) -> float:
        '''What one autoit.mouse_click() costs us, given the hold we asked AutoIt for.'''
        return CLICK_BASE + self.click_hold / 1000.0

    def cell_floor(self) -> float:
        '''Work that must happen inside a cell's budget. Speed stops having any effect once
        the frame budget drops below this, so the UI and the ETA can say so instead of lying.'''
        # Interpolation never raises the floor: a glide sheds hops to fit its budget (PencilTool._move).
        if not self.hold_stroke:
            return 4 * MOVE_COST + 4 * self.click_cost          # move + 3 jitter-clicks + the real one
        return max(MOVE_COST,                                   # stroke continues: a single move
                   4 * MOVE_COST + PRESS_COST)                  # stroke start: move + jitter + the press

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
                # `glide` (the old AutoIt 1-100 speed scale) is deliberately not migrated:
                # it meant the opposite of this and every value of it blew the frame budget.
                glide_steps=min(16, max(1, int(d.get("glide_steps", base.glide_steps)))),
                click_hold=min(20, max(0, int(d.get("click_hold", base.click_hold)))),
            )
        except (TypeError, ValueError):
            return base


def adjacent(a, b) -> bool:
    '''True when grid cells a and b touch (8 directions).'''
    return a is not None and b is not None and max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 1


class TimingStats:
    '''What a draw actually cost, per cell. Without this a blown frame budget is invisible:
    the pencil just stops sleeping and Speed quietly does nothing.'''

    def __init__(self):
        self.reset()

    def reset(self):
        self.cells = 0
        self.overruns = 0       # cells that took longer than the budget allowed
        self.total = 0.0
        self.worst = 0.0

    def add(self, elapsed: float, overrun: float):
        self.cells += 1
        self.total += elapsed
        self.worst = max(self.worst, elapsed)
        if overrun > 0.0005:                       # ignore sub-half-ms scheduling noise
            self.overruns += 1

    @property
    def mean(self) -> float:
        return self.total / self.cells if self.cells else 0.0

    def summary(self) -> str:
        if not self.cells:
            return "no cells drawn"
        pct = 100.0 * self.overruns / self.cells
        return (f"{self.cells} cells, {self.mean * 1000:.1f} ms/cell avg, "
                f"{self.worst * 1000:.1f} ms worst, {self.overruns} over budget ({pct:.0f}%)")


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
        self._pos = None       # where we last put the cursor, so a glide knows where to start
        self.stats = TimingStats()

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
        self._pos = None
        self.stats.reset()

    # ---- cost model --------------------------------------------------------
    @property
    def click_cost(self) -> float:
        return self.pen.click_cost

    def cell_floor(self) -> float:
        '''See PenSettings.cell_floor: the per-cell work Speed cannot squeeze below.'''
        return self.pen.cell_floor()

    # ---- movement ----------------------------------------------------------
    def _move(self, x, y, budget: float = 0.0):
        '''Teleport, or walk there in a few hops spread across `budget`.

        AutoIt's own paced move is unusable here: 13 px at speed 5 blocks for ~102 ms
        regardless of FPS or Speed, which is what made interpolated draws ignore the
        slider entirely. We step it ourselves so a glided cell costs exactly one frame.'''
        x, y = int(x), int(y)
        start, self._pos = self._pos, (x, y)
        n = 1
        if self.pen.interpolate and start is not None and budget > 0:
            n = max(1, min(self.pen.glide_steps, int(budget / GLIDE_SLICE)))
        if n == 1:
            autoit.mouse_move(x, y, 0)
            return
        x0, y0 = start
        t0, slot = time.perf_counter(), budget / n
        for i in range(1, n + 1):
            autoit.mouse_move(round(x0 + (x - x0) * i / n), round(y0 + (y - y0) * i / n), 0)
            left = slot * i - (time.perf_counter() - t0)
            if left > 0:
                time.sleep(left)

    def _wait_frame(self, t0: float, budget: float, reserve: float = 0.0) -> float:
        '''Sleep until `budget` has passed since t0, minus whatever the caller still has to do
        (`reserve`), so every mode costs one frame end to end. Returns the overrun.'''
        left = budget - reserve - (time.perf_counter() - t0)
        if left > 0:
            time.sleep(left)
        return -left

    def _jitter(self, x, y, budget: float):
        # This many inputs is because roblox sucks: it registers presses better with motion.
        nudge = min(0.001, budget / 10)
        autoit.mouse_move(x + 1, y + 1, 0)
        time.sleep(nudge)
        autoit.mouse_move(x - 1, y - 1, 0)
        time.sleep(nudge)
        autoit.mouse_move(x, y, 0)
        self._pos = (int(x), int(y))

    # ---- legacy: click every cell (one frame per cell) --------------------
    def draw_at(self, x, y, budget: float = None):
        '''Roblox registers a press better with motion around it, so the click is repeated
        across a 1 px jitter. With AutoIt's click delays off that costs ~1 ms, not ~82 ms,
        so all four clicks still fit inside a single frame.'''
        budget = self.settings.get_frame_sleep_time() if budget is None else budget
        t0 = time.perf_counter()
        nudge = min(0.001, budget / 10)
        self._move(x, y, budget / 2)          # leave half the frame for the click sequence
        autoit.mouse_click()
        autoit.mouse_move(x + 1, y + 1, 0)
        time.sleep(nudge)
        autoit.mouse_click()
        autoit.mouse_move(x - 1, y - 1, 0)
        time.sleep(nudge)
        autoit.mouse_click()
        autoit.mouse_move(x, y, 0)
        self._pos = (int(x), int(y))
        over = self._wait_frame(t0, budget, reserve=self.click_cost)
        autoit.mouse_click()                  # lands at the end of the frame, as it always did
        self.stats.add(time.perf_counter() - t0, over)

    def draw_color_at(self, color: str, x, y):
        self.color_picker.pick(color)
        self.draw_at(x, y)

    # ---- the seam the Drawer calls ---------------------------------------
    def draw_step(self, step) -> None:
        '''One cell = one frame in every mode; hold on/off and teleport/interpolate only change
        what happens inside that frame. Only the configured pen/color delays add time.'''
        budget = self.settings.get_frame_sleep_time()
        x, y = self.settings.cell_center(step.gx, step.gy)
        if step.color != self.color_picker.current_color:
            self.pen_up()
            self.color_picker.pick(step.color)
            time.sleep(self.pen.color_delay)
            self._pos = None                      # the picker walked the cursor off the canvas
        if not self.pen.hold_stroke:
            self.draw_at(x, y, budget)
            return
        cell = (step.gx, step.gy)
        if self._down and adjacent(self._last, cell):
            t0 = time.perf_counter()
            self._move(x, y, budget)              # stroke continues: the game paints the cell on the next frame
            over = self._wait_frame(t0, budget)
        else:
            self.pen_up()                         # too far: hop with the pen up, then start a new stroke
            t0 = time.perf_counter()
            self._move(x, y, budget / 2)          # leave room for the jitter and the press
            self._jitter(x, y, budget)
            over = self._wait_frame(t0, budget, reserve=PRESS_COST)
            self.pen_down()                       # pressed at the end of the frame, where a legacy click lands
        self.stats.add(time.perf_counter() - t0, over)
        self._last = cell

    @staticmethod
    def move_to(x, y):
        autoit.mouse_move(int(x), int(y), 0)
