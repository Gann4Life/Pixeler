# TODO: Possibility to load image from clipboard.

import keyboard
import questionary
import time
from playsound import playsound

from modules.calibration import ScreenCalibration
from modules.image_process import PixelExtractor
from modules.input_control import ColorPicker, PencilTool

class PixelerApp:
    def __init__(self):
        self.pixelIndex = 0
        self.should_stop = False
        
        self.image_pixels = PixelExtractor()

        self.settings = ScreenCalibration()
        self.settings.load_config()
        self.color_picker = ColorPicker(self.settings)
        self.pencil = PencilTool(self.settings, self.color_picker)

        self.main_menu()

    def main_menu(self):
        options = {
            "Calibrate Screen": self.calibrate,
            "Begin Drawing": self.begin_drawing,
            "Load Image from File": self.image_pixels.load_image_file,
            "Load Image from Clipboard": self.image_pixels.load_image_clipboard,
            "Exit": exit
        }

        choice = questionary.rawselect("Select an option:", choices=options.keys()).ask()
        options[choice]()
        self.main_menu()

    def calibrate(self):
        self.settings.run()

    def begin_drawing(self):
        # Warn user if coordinates are not set properly
        if not(self.settings.is_config_valid()):
            print("Error: Please calibrate the screen first to set all necessary coordinates.")
            playsound("audio/error.mp3")
            self.main_menu()
            return

        print("Press F To Start Drawing")
        print("Press G To Stop and Return to Menu")
        
        self.should_stop = False
        
        # Manual loop instead of keyboard.wait()
        while True:
            if keyboard.is_pressed('f') and len(self.image_pixels.get_pixels()) > 0:
                self.draw_loop()
            elif keyboard.is_pressed('g'):
                self.stop()
                break  # Exit loop and go back to menu
            time.sleep(0.05)  # Small delay to prevent CPU spinning

    def draw_loop(self):
        print("Drawing started...")
        print(self.settings.y)

        palette = set(self.image_pixels.get_pixels())
        for c in palette:
            self.color_picker.pick(c)
            self.pixelIndex = 0
            for y in range(len(self.settings.y)):
                if self.should_stop:
                    break

                for x in range(len(self.settings.x)):
                    if self.should_stop:
                        break

                    current_color = self.image_pixels.get_color_at(x, y)
                    if current_color != c: continue

                    self.pencil.draw_at(self.settings.x[x], self.settings.y[y])
                    self.pixelIndex += 1

                    # Check for stop key during drawing
                    if keyboard.is_pressed('g'):
                        print("Stopping...")
                        self.should_stop = True
                        break

        print("Drawing complete!")
        playsound("audio/ding.mp3")

    def stop(self):
        print("\nStopping... Returning to main menu.")
        self.should_stop = True
        self.pixelIndex = 0  # Reset progress
        keyboard.unhook_all()  # Clean up all keyboard listeners
        self.main_menu()
        
if __name__ == "__main__":
    app = PixelerApp()