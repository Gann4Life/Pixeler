import keyboard
import json
import questionary
from playsound import playsound
from pynput import mouse

class FramerateValidator(questionary.Validator):
    def validate(self, document):
        try:
            value = int(document.text)
            if value <= 0: raise ValueError
        except Exception:
            raise questionary.ValidationError(message="Only numbers superior to zero are allowed.")

class ScreenCalibration:
    def __init__(self):
        self.last_click_position = (0, 0)
        self.listen_mouse = False

        self.config_filename = 'config.json'
        self.cancel_calibration = False

        self.fps = 0
        self.x = []
        self.y = []
        self.colorCord = [0, 0]
        self.inputCord = [0, 0]
        self.closeCord = [0, 0]

    def wait_for_user_click(self):
        """Wait until the user clicks, then return (x, y, button)."""
        result = {}

        def on_click(x, y, button, pressed):
            if pressed and button == mouse.Button.left:
                result['pos'] = (x, y, button)
                listener.stop()  # stop the listener to end the blocking call

        listener = mouse.Listener(on_click=on_click)
        listener.start()
        listener.join()  # blocks until listener.stop() is called
        return result['pos']
    
    def get_left_click_point(self):
        x, y, btn = self.wait_for_user_click()
        return (x, y)

    def run(self, on_finish: callable = None):
        calibrating = True
        def leave(): 
            nonlocal calibrating
            calibrating = False
            print("[Calibratoin] Leaving.")
        
        # print("\nWARNING: All mouse clicks will be recorded now, please be as precise as you can.\n")

        while calibrating:
            options = {
                "Set framerate": self.ask_fps,
                "Step 1: Horizontal pixels": self.step1,
                "Step 2: Vertical pixels": self.step2,
                "Step 3: Color picker position": self.step3,
                "Step 4: Color picker's hex input field": self.step4,
                "Step 5: Color picker's close button": self.step5,
                "Save": self.save_config,
                "Exit": leave
            }

            choice = questionary.rawselect("Pick a setting to calibrate", choices=options.keys()).ask()
            options[choice]()

    def ask_fps(self):
        print("Tip: use SHIFT + F5 in roblox to view your FPS.")
        self.fps = int(questionary.text("Enter your Roblox average FPS", "30", validate=FramerateValidator).ask())
        print(f"Optimal delay is: {self.get_frame_sleep_time():.4f} seconds")

    def step1(self):
        # Ask to click top side pixels left to right
        print("1. Click all pixels in the top side of the canvas, from left to right.")
        newx = []
        while len(newx) != 32:          
            x, y = self.get_left_click_point()
            newx.append(x)
            playsound("audio/xpop.wav")
        self.x = newx
        playsound("audio/ding.mp3")

    def step2(self):
        # Ask to click left side pixels top to bottom
        print("2. Click all pixels in the left side of the canvas, from top to bottom.")
        newy = []
        while len(newy) != 32:
            x, y = self.get_left_click_point()
            newy.append(y)
            playsound("audio/ypop.wav")
        self.y = newy
        playsound("audio/ding.mp3")

    def step3(self):
        # Ask to click color picker location
        print("3. Click where the color picker is located.")
        self.colorCord = self.get_left_click_point()
        print(self.colorCord)
        playsound("audio/xpop.wav")

    def step4(self):
        # Ask to click color picker hex input
        print("4. Click where the color text input is located.")
        self.inputCord = self.get_left_click_point()
        print(self.inputCord)
        playsound("audio/xpop.wav")

    def step5(self):
        # Ask to click color picker's close button
        print("5. Click where the color picker's close button is located.")
        self.closeCord = self.get_left_click_point()
        print(self.closeCord)
        playsound("audio/ypop.wav")
    
    def save_and_exit(self, on_finish: callable = None):
        if not(self.is_config_valid()):
            print("You must set all coordinates before exiting!")
            playsound("audio/error.mp3")
            return False  # Indicate failure
        
        self.save_config(self.config_filename)
        playsound("audio/ding.mp3")
        
        keyboard.unhook_all()  # Clean up keyboard listeners
        
        if on_finish:
            on_finish()
        
        return True  # Indicate success
    
    def is_config_valid(self):
        return (len(self.x) == 32 and len(self.y) == 32 and
                self.colorCord != [0, 0] and
                self.inputCord != [0, 0] and
                self.closeCord != [0, 0] and
                self.fps > 0)
    
    # This Functions makes sure that it can run smooth without any problems based on Your FPS
    def get_frame_sleep_time(self):
            frame_time = 1 / self.fps

            # We'll use a slightly longer sleep time to ensure the game registers the input
            f_sleep_time = frame_time * 1.2

            return f_sleep_time

    def save_config(self, filepath='config.json'):
        playsound("audio/ding.mp3", False)
        config_data = {
            "fps": self.fps,
            "colorCord": self.colorCord,
            "inputCord": self.inputCord,
            "closeCord": self.closeCord,
            "x": self.x,
            "y": self.y,
        }
        with open(filepath, 'w+') as config_file:
            json.dump(config_data, config_file, indent=4)
        print("Configuration saved to", filepath)
    
    def load_config(self, filepath='config.json'):
        try:
            with open(filepath, 'r') as config_file:
                config_data = json.load(config_file)
                self.fps = config_data.get("fps", 0)
                self.colorCord = config_data.get("colorCord", [0, 0])
                self.inputCord = config_data.get("inputCord", [0, 0])
                self.closeCord = config_data.get("closeCord", [0, 0])
                self.x = config_data.get("x", [])
                self.y = config_data.get("y", [])
            print("Configuration loaded from config.json.")
        except FileNotFoundError:
            print("No configuration file found. Please run calibration.")
            playsound("audio/error.mp3")
        except json.JSONDecodeError:
            print("Error decoding JSON from the configuration file.")
            playsound("audio/error.mp3")
