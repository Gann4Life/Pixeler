import os
import threading

from playsound import playsound

AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'resources', 'audio')


class Audio:
    @staticmethod
    def play(audio_name: str, block: bool = False):
        '''Plays an audio file under resources/audio/ (non-blocking by default).'''
        path = os.path.join(AUDIO_DIR, audio_name)
        if block:
            _safe_play(path)
        else:
            threading.Thread(target=_safe_play, args=(path,), daemon=True).start()

    @staticmethod
    def play_error(block: bool = False):
        Audio.play("sfx Error.mp3", block)

    @staticmethod
    def play_ding(block: bool = False):
        Audio.play("sfx Success.mp3", block)

    @staticmethod
    def play_xpop(block: bool = False):
        Audio.play("sfx XPop.mp3", block)

    @staticmethod
    def play_ypop(block: bool = False):
        Audio.play("sfx YPop.mp3", block)


def _safe_play(path: str):
    try:
        playsound(path, True)
    except Exception as e:  # playsound is flaky; never let a sound crash the app
        print(f"[audio] could not play {path}: {e}")
