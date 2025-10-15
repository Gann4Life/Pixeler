from ..calibration import ScreenCalibration
import keyboard, autoit, time

class ColorPicker:
    def __init__(self, settings: ScreenCalibration):
        self.settings = settings
        self.current_color = ""

    def pick(self, color: str) -> None:
        if self.current_color == color:
            return

        self.open()
        self.current_color = color
        self.write_color(self.current_color)
        self.close()

    def open(self) -> None:
        cY, cX = self.settings.colorCord
        autoit.mouse_move(cY, cX, 0)
        time.sleep(self.settings.get_frame_sleep_time())
        autoit.mouse_move(cY+1, cX+1, 0)
        time.sleep(0.005)
        autoit.mouse_move(cY-1, cX-1, 0)
        time.sleep(self.settings.get_frame_sleep_time())
        autoit.mouse_click()

    def write_color(self, color: str) -> None:
        iY, iX = self.settings.inputCord
        autoit.mouse_move(iY, iX, 0)
        time.sleep(self.settings.get_frame_sleep_time())
        autoit.mouse_move(iY+1, iX+1, 0)
        time.sleep(0.005)
        autoit.mouse_move(iY-1, iX-1, 0)
        time.sleep(self.settings.get_frame_sleep_time())
        autoit.mouse_click()

        keyboard.write(color)

    def close(self) -> None:
        clY, clX = self.settings.closeCord
        autoit.mouse_move(clY, clX, 0)
        time.sleep(self.settings.get_frame_sleep_time())
        autoit.mouse_move(clY+1, clX+1, 0)
        time.sleep(0.005)
        autoit.mouse_move(clY-1, clX-1, 0)
        time.sleep(self.settings.get_frame_sleep_time())
        autoit.mouse_click()

class PencilTool:
    def __init__(self, settings: ScreenCalibration, color_picker: ColorPicker):
        self.settings = settings
        self.color_picker = color_picker

    def draw_at(self, x, y, speed=0):
        # This many inputs is because roblox sucks
        autoit.mouse_move(x, y, speed)
        time.sleep(0.001)
        autoit.mouse_click()
        autoit.mouse_move(x+1, y+1, speed)
        time.sleep(0.001)
        autoit.mouse_click()
        autoit.mouse_move(x-1, y-1, speed)
        time.sleep(0.001)
        autoit.mouse_click()
        autoit.mouse_move(x, y, speed)
        time.sleep(self.settings.get_frame_sleep_time())
        autoit.mouse_click()

    def draw_color_at(self, color: str, x, y):
        self.color_picker.pick(color)
        self.draw_at(x, y, 0)