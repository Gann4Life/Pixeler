import keyboard
import time
import threading
from tkinter import *
from tkinter.font import Font

from modules.resources import Audio
from modules.calibration import ScreenCalibration
from modules.image_process import PixelExtractor
from modules.input_control import ColorPicker, PencilTool

class PixelerGUI:
    def __init__(self, root : Tk, app):
        self.app = app
        app.set_gui(self)

        FONT =  Font(size=20)

        self.root = root
        self.root.state("zoomed")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", "blue")
        self.root.configure(bg="blue")

        self.btnClose = Button(self.root, text="❌", command=exit, foreground='white', background='black', font=FONT)
        self.btnClose.grid(column=0, row=0)

        self.btnCalibrate = Button(self.root, text="⚙", command=self.calibrate, foreground='white', background='black', font=FONT)
        self.btnCalibrate.grid(column=1, row=0)

        self.btnDraw = Button(self.root, text=f"✏", command=self.draw, foreground='white', background='black', font=FONT)
        self.btnDraw.grid(column=2, row=0)

        self.btnLoadFile = Button(self.root, text="📁", command=self.load_file, foreground='white', background='black', font=FONT)
        self.btnLoadFile.grid(column=3, row=0)

        self.btnLoadClipboard = Button(self.root, text="📋", command=self.laod_clipboard, foreground='white', background='black', font=FONT)
        self.btnLoadClipboard.grid(column=4, row=0)

        self.lblActivityInfo = Label(self.root, text="| Close | Calibrate | Draw | Load File | Load Clipboard |", foreground='white', background='black', font=FONT)
        self.lblActivityInfo.grid(column=5, row=0)

    def calibrate(self):
        self.display_message('[ CALIBRATION MODE ] Please check the console for a step by step guide.')
        self.btnCalibrate.grid_remove()
        threading.Thread(target=self.app.calibrate, daemon=True).start()

    def draw(self):
        self.display_message("[ DRAW MODE ] Press F to start drawing and toggle pause, press G to stop completely.")
        self.btnDraw.grid_remove()
        threading.Thread(target=self.app.begin_drawing, daemon=True).start()

    def reset(self):
        self.lblActivityInfo.configure(text="| Close | Calibrate | Draw | Load File | Load Clipboard |")
        self.btnDraw.grid()
        self.btnCalibrate.grid()

    def load_file(self):
        self.app.image_pixels.load_image_file()

    def laod_clipboard(self):
        self.app.image_pixels.load_image_clipboard()

    def display_message(self, message : str) -> None:
        self.lblActivityInfo.configure(text=message)

    def display_error(self, message : str) -> None:
        self.lblActivityInfo.configure(text=f"ERROR: {message}", foreground='red')

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

    #     self.main_menu()
    def set_gui(self, gui : PixelerGUI):
        self.gui = gui

    def main_menu(self):
        self.gui.reset()

    def calibrate(self):
        self.settings.run()
        self.main_menu()

    def begin_drawing(self):
        # Warn user if coordinates are not set properly
        if not(self.settings.is_config_valid()):
            print("Error: Please calibrate the screen first to set all necessary coordinates.")
            Audio.play_error()
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
        if self.image_pixels.image is None:
            self.gui.display_error("Please load an image first.")
            self.gui.btnDraw.grid()
            Audio.play_error()
            return

        print("Drawing started...")
        self.stopped = False

        # Draw colors in aplhabetical order cuz why not (prioritizes darker colors I think OwO)
        palette = sorted(set(self.image_pixels.get_pixels()))

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
        Audio.play_ding()

    def stop(self):
        print("\nStopping... Returning to main menu.")
        self.pixelIndex = 0  # Reset progress
        self.paused = True
        self.stopped = True
        keyboard.unhook_all()  # Clean up all keyboard listeners
        self.main_menu()

if __name__ == "__main__":
    app = PixelerApp()
    root = Tk()
    gui = PixelerGUI(root, app)
    root.mainloop()