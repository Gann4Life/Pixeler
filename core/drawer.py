'''Worker that executes DrawSteps in the game. Owns play/pause/stop and reports
progress through Qt signals (emitted from the worker thread, delivered on the
UI thread via queued connections).

Every start and resume is "armed": the worker waits until no key is held (so a
hotkey that triggered Play can't leak into the game) and then waits
`start_delay` seconds before the first click.'''
import threading
import time

import keyboard
from PySide6.QtCore import QObject, Signal

from .actuator import PencilTool
from .audio import Audio

IDLE, RUNNING, PAUSED = 'idle', 'running', 'paused'
MODIFIERS = ("ctrl", "shift", "alt", "windows")


def any_key_pressed() -> bool:
    pressed = getattr(keyboard, "_pressed_events", None)
    if isinstance(pressed, dict):
        return bool(pressed)
    return any(keyboard.is_pressed(k) for k in MODIFIERS)


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
            self.pencil.color_picker.reset()   # the user may have scrubbed
            self._set_state(RUNNING)
            self._resume.set()
            return
        if not self.steps:
            self.error.emit("Nothing to draw. Load an image first.")
            Audio.play_error()
            return
        self._stop.clear()
        self._resume.set()
        self.pencil.color_picker.reset()
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
        self.message.emit("Drawing…")
        return True

    def _run(self):
        completed = False
        armed = False
        try:
            while True:
                if self._stop.is_set():
                    break
                if not self._resume.is_set():
                    armed = False
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
            if completed:
                Audio.play_ding()
            self._next_index = 0          # Stop / done -> timeline back to the start
            self.progress.emit(0)
            self._set_state(IDLE)
            self.finished.emit(completed)

    def _set_state(self, state: str):
        self.state = state
        self.state_changed.emit(state)
