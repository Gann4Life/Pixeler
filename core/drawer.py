'''Worker that executes DrawSteps in the game. Owns play/pause/stop and reports
progress through Qt signals (emitted from the worker thread, delivered on the
UI thread via queued connections).'''
import threading

from PySide6.QtCore import QObject, Signal

from .actuator import PencilTool
from .audio import Audio

IDLE, RUNNING, PAUSED = 'idle', 'running', 'paused'


class Drawer(QObject):
    progress = Signal(int)        # number of steps completed (== index of the next step)
    state_changed = Signal(str)   # IDLE / RUNNING / PAUSED
    finished = Signal(bool)       # True = reached the end, False = stopped early
    error = Signal(str)

    def __init__(self, pencil: PencilTool, parent=None):
        super().__init__(parent)
        self.pencil = pencil
        self.steps = []
        self.state = IDLE
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
    def _run(self):
        completed = False
        try:
            while True:
                if self._stop.is_set():
                    break
                if not self._resume.is_set():
                    self._resume.wait()
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
