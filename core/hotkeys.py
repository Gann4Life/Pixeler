'''Global hotkeys (work while the game has focus) built on the `keyboard` module.

Defaults use Ctrl+Shift so they never type into Roblox chat and don't collide
with AltGr (= Ctrl+Alt) characters on Spanish / Latin-American layouts. The
main key must not be one Roblox acts on regardless of modifiers (Space jumps!).
Key strings are in `keyboard` format: "ctrl+shift+space".
'''
import keyboard
from PySide6.QtCore import QObject, Signal

ACTIONS = [
    # (action id, label, default key)
    ("play_pause",     "Play / Pause",        "ctrl+shift+p"),
    ("stop",           "Stop",                "ctrl+shift+x"),
    ("load_file",      "Load image file",     "ctrl+shift+l"),
    ("load_clipboard", "Load from clipboard", "ctrl+shift+v"),
    ("reset_crop",     "Reset crop",          "ctrl+shift+r"),
    ("toggle_panels",  "Show / hide panels",  "ctrl+shift+h"),
]
DEFAULTS = {a: k for a, _, k in ACTIONS}
LABELS = {a: l for a, l, _ in ACTIONS}

# Old defaults that turned out to trigger game actions; saved bindings using them are upgraded.
RETIRED = {"ctrl+shift+space": "play_pause", "ctrl+shift+o": "load_file"}

# Keys Roblox acts on even while a modifier is held (jump, walk, camera zoom, menu, leaderboard, chat).
ROBLOX_KEYS = {"space": "jump", "w": "walk", "a": "walk", "s": "walk", "d": "walk",
               "i": "camera zoom", "o": "camera zoom", "esc": "menu", "tab": "leaderboard",
               "/": "chat", "enter": "chat", "backspace": "chat"}


def roblox_conflict(key: str):
    '''Returns what Roblox does with the main key of `key`, or None if it looks safe.'''
    if not key:
        return None
    for p in key.lower().split("+"):
        if p not in ("ctrl", "shift", "alt", "windows") and p in ROBLOX_KEYS:
            return ROBLOX_KEYS[p]
    return None


def pretty(key: str) -> str:
    '''"ctrl+shift+space" -> "Ctrl+Shift+Space" for tooltips.'''
    if not key:
        return "unbound"
    return "+".join(p.capitalize() for p in key.split("+"))


class HotkeyManager(QObject):
    triggered = Signal(str)   # action id; emitted from keyboard's thread, queued to the UI

    def __init__(self, bindings: dict = None, parent=None):
        super().__init__(parent)
        self.bindings = dict(DEFAULTS)
        if bindings:
            for a, k in bindings.items():
                if a not in DEFAULTS:
                    continue
                if k in RETIRED and RETIRED[k] == a:
                    k = DEFAULTS[a]          # upgrade a retired default
                self.bindings[a] = k
        self._handles = {}
        self.enabled = True

    def start(self):
        for action in self.bindings:
            self._register(action)

    def stop(self):
        for action in list(self._handles):
            self._unregister(action)

    def rebind(self, action: str, key: str) -> bool:
        '''Returns False if `keyboard` rejects the combination.'''
        key = (key or "").strip().lower()
        self._unregister(action)
        self.bindings[action] = key
        return self._register(action)

    def key_for(self, action: str) -> str:
        return self.bindings.get(action, "")

    def tooltip(self, action: str, text: str = None) -> str:
        return f"{text or LABELS[action]}  ({pretty(self.key_for(action))})"

    # ---- internals ---------------------------------------------------------
    def _register(self, action: str) -> bool:
        key = self.bindings.get(action)
        if not key:
            return False
        try:
            self._handles[action] = keyboard.add_hotkey(
                key, self._fire, args=(action,), suppress=False, trigger_on_release=False)
            return True
        except (ValueError, KeyError) as e:
            print(f"[hotkeys] cannot bind {action} to '{key}': {e}")
            return False

    def _unregister(self, action: str):
        h = self._handles.pop(action, None)
        if h is not None:
            try:
                keyboard.remove_hotkey(h)
            except (KeyError, ValueError):
                pass

    def _fire(self, action: str):
        if self.enabled:
            self.triggered.emit(action)
