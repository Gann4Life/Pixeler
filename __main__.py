import keyboard
import questionary
import time
import threading
from playsound import playsound

from modules.calibration import ScreenCalibration
from modules.image_process import PixelExtractor
from modules.input_control import ColorPicker, PencilTool

class PixelerApp:
    def __init__(self):
        self.pixelIndex = 0
        
        self.paused = True
        self.stopped = False

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
        
        draw_process = threading.Thread(target=self.draw_loop, daemon=True)
        draw_process.start()

        def toggle_pause():
            self.paused = not(self.paused)
            if self.paused:
                print("Paused! Press F to resume.")
            else:
                print("Resuming...")    

        keyboard.on_press_key('f', lambda _: toggle_pause())
        keyboard.wait('g')

        self.stop()

    def draw_loop(self):
        print("Drawing started...")
        self.stopped = False

        palette = set(self.image_pixels.get_pixels())
        for c in palette:
            self.pixelIndex = 0

            for y in range(len(self.settings.y)):
                for x in range(len(self.settings.x)):
                    
                    if self.stopped: return
                    while self.paused:
                        if self.stopped: return
                        time.sleep(0.1)
                    
                    current_color = self.image_pixels.get_color_at(x, y)
                    if current_color != c: continue

                    #self.color_picker.pick(c)
                    self.pencil.draw_color_at(c, self.settings.x[x], self.settings.y[y])
                    self.pixelIndex += 1

                    

        print("Drawing complete!")
        playsound("audio/ding.mp3")

    def stop(self):
        print("\nStopping... Returning to main menu.")
        self.pixelIndex = 0  # Reset progress
        self.paused = True
        self.stopped = True
        keyboard.unhook_all()  # Clean up all keyboard listeners
        self.main_menu()
        
if __name__ == "__main__":
    app = PixelerApp()