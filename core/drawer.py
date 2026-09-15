'''Worker that executes DrawSteps in the game. Owns play/pause/stop and reports
progress through Qt signals (emitted from the worker thread, delivered on the
UI thread via queued connections).

Every start and resume is "armed": the worker waits until no key is held (so a
hotkey that triggered Play can't leak into the game) and then waits
`start_delay` seconds before the first click.'''
import contextlib
import threading
import time

import keyboard
from PySide6.QtCore import QObject, Signal

from .actuator import PencilTool, focus_game
from .audio import Audio

IDLE, RUNNING, PAUSED = 'idle', 'running', 'paused'
MODIFIERS = ("ctrl", "shift", "alt", "windows")


def any_key_pressed() -> bool:
    pressed = getattr(keyboard, "_pressed_events", None)
    if isinstance(pressed, dict):
        return bool(pressed)
    return any(keyboard.is_pressed(k) for k in MODIFIERS)


def timer_resolution(ms):
    '''Ask Windows for a finer scheduler tick (1 ms) while drawing so `time.sleep(frame)` is
    accurate; pass None to release it. No-op elsewhere.'''
    with contextlib.suppress(Exception):
        import ctypes
        winmm = ctypes.windll.winmm
        (winmm.timeBeginPeriod if ms else winmm.timeEndPeriod)(ms or 1)


class Drawer(QObject):
    progress = Signal(int)        # number of steps completed (== index of the next step)
    state_changed = Signal(str)   # IDLE / RUNNING / PAUSED
    message = Signal(str)         # human-readable progress ("Release all keys…", "Starting in 1.2s")
    finished = Signal(bool)       # True = reached the end, False = stopped early
    error = Signal(str)

    def __init__(self, pencil: PencilTool, parent=None):
        super().__init__(parent)
        self.pencil = pencil
        self.steps = []
        self.state = IDLE
        self.start_delay = 1.5
        self._thread = None
        self._resume = threading.Event()
        self._stop = threading.Event()
        self._next_index = 0

    # ---- public API (UI thread) --------------------------------------------
    def set_steps(self, steps: list):
        '''Only allowed while not running; the UI enforces that.'''
        self.steps = list(steps)
        self._next_index = min(self._next_index, len(self.steps))

    def play(self, from_index: int = None):
        if self.state == RUNNING:
            return
        if from_index is not None:
            self._next_index = max(0, min(int(from_index), len(self.steps)))
        if self.state == PAUSED:
            self.pencil.reset()                # the user may have scrubbed; pen is up already
            self._set_state(RUNNING)
            self._resume.set()
            return
        if not self.steps:
            self.error.emit("Nothing to draw. Load an image first.")
            Audio.play_error()
            return
        self._stop.clear()
        self._resume.set()
        self.pencil.reset()
        self._set_state(RUNNING)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def pause(self):
        if self.state == RUNNING:
            self._resume.clear()
            self._set_state(PAUSED)

    def toggle(self):
        if self.state == RUNNING:
            self.pause()
        else:
            self.play()

    def stop(self):
        if self.state == IDLE:
            return
        self._stop.set()
        self._resume.set()   # wake a paused worker so it can exit

    def seek(self, index: int):
        '''Move the playhead (pauses first if running).'''
        if self.state == RUNNING:
            self.pause()
        self._next_index = max(0, min(int(index), len(self.steps)))
        self.progress.emit(self._next_index)

    @property
    def next_index(self) -> int:
        return self._next_index

    # ---- worker thread -------------------------------------------------------
    def _interrupted(self) -> bool:
        '''True if the worker should leave the arming phase (stop or pause).'''
        return self._stop.is_set() or not self._resume.is_set()

    def _arm(self) -> bool:
        '''Wait for all keys to be released, then for start_delay. Returns False if interrupted.'''
        announced = False
        while any_key_pressed():
            if self._interrupted():
                return False
            if not announced:
                self.message.emit("Release all keys to start…")
                announced = True
            time.sleep(0.03)
        deadline = time.time() + max(0.0, self.start_delay)
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            if self._interrupted():
                return False
            if any_key_pressed():          # a key went down during the countdown: start over
                return self._arm()
            self.message.emit(f"Starting in {remaining:.1f}s — keep your hands off the keyboard")
            time.sleep(min(0.1, remaining))
        if not focus_game():
            self.message.emit("Drawing… (no Roblox window found, clicking where the mouse lands)")
        else:
            self.message.emit("Drawing…")
        return True

    def _run(self):
        completed = False
        armed = False
        try:
            timer_resolution(1)     # Python 3.10 sleeps in ~15.6 ms ticks on Windows: a 20 ms frame took 31 ms
            while True:
                if self._stop.is_set():
                    break
                if not self._resume.is_set():
                    armed = False
                    self.pencil.pen_up()
                    self.message.emit("Paused.")
                    self._resume.wait()
                    continue
                if not armed:
                    armed = self._arm()
                    continue
                i = self._next_index
                if i >= len(self.steps):
                    completed = True
                    break
                self.pencil.draw_step(self.steps[i])
                self._next_index = i + 1
                self.progress.emit(self._next_index)
        except Exception as e:  # autoit / keyboard failures
            self.error.emit(str(e))
            Audio.play_error()
        finally:
            timer_resolution(None)
            try:
                self.pencil.pen_up()
            except Exception as e:  # noqa: BLE001
                print(f"[pen] could not release the button: {e}")
            stats = self.pencil.stats
            if stats.cells:
                target = self.pencil.settings.get_frame_sleep_time() * 1000
                print(f"[timing] {stats.summary()} (budget {target:.1f} ms/cell)")
                if stats.overruns > stats.cells * 0.1:
                    print("[timing] the frame budget is below what this pen mode costs - "
                          "Speed is capped; lower FPS, raise Speed less, or simplify the pen settings")
            if completed:
                Audio.play_ding()
            self._next_index = 0          # Stop / done -> timeline back to the start
            self.progress.emit(0)
            self._set_state(IDLE)
            self.finished.emit(completed)

    def _set_state(self, state: str):
        self.state = state
        self.state_changed.emit(state)
