# TODO: Possibility to load image from clipboard.

from modules.calibration import ScreenCalibration
import keyboard, autoit, time
import tkinter as tk
from tkinter import filedialog
from PIL import Image
from playsound import playsound
import questionary

class PixelerApp:
    def __init__(self):
        self.pIndex = 0
        self.pixels = []
        self.should_stop = False

        self.settings = ScreenCalibration()
        self.settings.load_config()
        color_picker = ColorPicker(self.settings)
        self.pencil = PencilTool(self.settings, color_picker)

        self.main_menu()

    def main_menu(self):
        options = {
            "Calibrate Screen": self.calibrate,
            "Begin Drawing": self.begin_drawing,
        }

        choice = questionary.rawselect("Select an option:", choices=options.keys()).ask()
        options[choice]()

    def calibrate(self):
        self.settings.run(on_finish=self.main_menu)

    def begin_drawing(self):
        # Warn user if coordinates are not set properly
        if not(self.settings.is_config_valid()):
            print("Error: Please calibrate the screen first to set all necessary coordinates.")
            playsound("audio/error.mp3")
            self.main_menu()
            return

        # TODO: Add option to load image from the menu, so we can redraw whenever we want without choosing the file every time we stop.
        print("Press H To Select Image")
        print("Press F To Start Drawing")
        print("Press G To Stop and Return to Menu")
        
        self.should_stop = False
        
        # Manual loop instead of keyboard.wait()
        while True:
            if keyboard.is_pressed('h'):
                self.process_image()
                time.sleep(0.3)  # Debounce to prevent multiple triggers
            elif keyboard.is_pressed('f') and len(self.pixels) > 0:
                self.draw_loop()
            elif keyboard.is_pressed('g'):
                self.stop()
                break  # Exit loop and go back to menu
            time.sleep(0.05)  # Small delay to prevent CPU spinning

    def process_image(self):
        self.pixels.clear()

        # Create a file dialog
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename()
        
        if not file_path:  # User cancelled
            print("No image selected.")
            return

        img = Image.open(file_path)

        if img.mode != 'RGBA':
            img = img.convert('RGBA')

        img = img.resize((32, 32))

        for y in range(img.height):
            for x in range(img.width):
                r, g, b, a = img.getpixel((x, y))
                color = "#{:02x}{:02x}{:02x}".format(r, g, b)
                self.pixels.append(color)
        
        self.pIndex = 0
        self.should_stop = False

        print(f"Opened image: {file_path}")
        print("Image loaded! Press F to start drawing.")

    # TODO: Change algorithm to draw all positions of each color in sequence.
    def draw_loop(self):
        print("Drawing started...")
        
        for cy in range(len(self.settings.y)):
            if self.should_stop:
                break
                
            for cx in range(len(self.settings.x)):
                if self.should_stop:
                    break
                
                # Check if we're done
                if self.pIndex >= 1024:
                    playsound("audio/ding.mp3")
                    print("Drawing complete!")
                    return

                self.pencil.draw_color_at(self.pixels[self.pIndex], self.settings.x[cx], self.settings.y[cy])
                self.pIndex += 1
                
                # Check for stop key during drawing
                if keyboard.is_pressed('g'):
                    print("Stopping...")
                    self.should_stop = True
                    break

    def stop(self):
        print("\nStopping... Returning to main menu.")
        self.should_stop = True
        self.pIndex = 0  # Reset progress
        self.pixels.clear()  # Clear loaded image
        keyboard.unhook_all()  # Clean up all keyboard listeners
        self.main_menu()

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
        
if __name__ == "__main__":
    app = PixelerApp()