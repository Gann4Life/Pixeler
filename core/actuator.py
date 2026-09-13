import time

import autoit
import keyboard

from .calibration import CalibrationModel


def _settle_click(x, y, sleep):
    '''Roblox needs a little jitter before it registers a click at a new spot.'''
    autoit.mouse_move(x, y, 0)
    time.sleep(sleep)
    autoit.mouse_move(x + 1, y + 1, 0)
    time.sleep(0.005)
    autoit.mouse_move(x - 1, y - 1, 0)
    time.sleep(sleep)
    autoit.mouse_click()


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
        keyboard.write(color)

    def close(self) -> None:
        x, y = self.settings.closeCord
        _settle_click(x, y, self.settings.get_frame_sleep_time())


class PencilTool:
    def __init__(self, settings: CalibrationModel, color_picker: ColorPicker):
        self.settings = settings
        self.color_picker = color_picker

    def draw_at(self, x, y, speed=0):
        # This many inputs is because roblox sucks
        autoit.mouse_move(x, y, speed)
        time.sleep(0.001)
        autoit.mouse_click()
        autoit.mouse_move(x + 1, y + 1, speed)
        time.sleep(0.001)
        autoit.mouse_click()
        autoit.mouse_move(x - 1, y - 1, speed)
        time.sleep(0.001)
        autoit.mouse_click()
        autoit.mouse_move(x, y, speed)
        time.sleep(self.settings.get_frame_sleep_time())
        autoit.mouse_click()

    def draw_color_at(self, color: str, x, y):
        self.color_picker.pick(color)
        self.draw_at(x, y, 0)

    def draw_step(self, step) -> None:
        '''Single seam the Drawer calls; a stroke-based engine can replace this later.'''
        x, y = self.settings.cell_center(step.gx, step.gy)
        self.draw_color_at(step.color, x, y)

    @staticmethod
    def move_to(x, y):
        autoit.mouse_move(int(x), int(y), 0)
