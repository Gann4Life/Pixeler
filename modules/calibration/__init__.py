import time
import pyautogui
import keyboard
import playsound
import json

class ScreenCalibration:
    def __init__(self):
        self.config_filename = 'config.json'

        self.fps = 0
        self.x = []
        self.y = []
        self.colorCord = [0, 0]
        self.inputCord = [0, 0]
        self.closeCord = [0, 0]
    
    def run(self, on_finish: callable = None):
        self.fps = int(input("\nEnter your Roblox Average FPS: "))
        print(f"Optimal delay is: {self.get_frame_sleep_time():.4f} seconds")

        print("\nPress |F| to add Mouse Coordinates to the List")
        print("Cooldown for each press is 0.1s \n")
        print("Press |T| to to add Color Button Coordinates to the List")
        print("Press |Y| to add Input area Coordinates to the List")
        print("Press |U| to add Close Button Coordinates to the List")
        print("Press |G| to save and exit.")
        
        # Use a manual loop instead of keyboard.wait()
        while True:
            if keyboard.is_pressed('f'):
                self.add_mouse_coordinate()
                time.sleep(0.3)  # Debounce
            elif keyboard.is_pressed('t'):
                self.set_color_button()
                time.sleep(0.3)
            elif keyboard.is_pressed('y'):
                self.set_input_area()
                time.sleep(0.3)
            elif keyboard.is_pressed('u'):
                self.set_close_button()
                time.sleep(0.3)
            elif keyboard.is_pressed('g'):
                if self.save_and_exit(on_finish):
                    break  # Only exit if save was successful
            time.sleep(0.05)  # Small delay to prevent CPU spinning
    
    def printValues(self):
        print(f"x = {self.x} y = {self.y} \n")
        print("Amount of X values are:", len(self.x))
        print("Amount of Y values are:", len(self.y))
        time.sleep(0.3)
    
    def printPercentage(self):
        percentage = len(self.x + self.y) / 64
        print(f"Progress: {round(percentage * 100)}%", end='\r')
    
    # ///
    def add_mouse_coordinate(self):
        cordX, cordY = pyautogui.position()
        if len(self.x) != 32:
            self.x.append(cordX)
            playsound.playsound("audio/xpop.wav")
            self.printPercentage()
        elif len(self.x) == 32 and len(self.y) != 32:
            self.y.append(cordY)
            playsound.playsound("audio/ypop.wav")
            self.printPercentage()
            if len(self.x) == 32 and len(self.y) == 32:
                playsound.playsound("audio/ding.mp3")
                self.printValues()
    
    def set_color_button(self):
        self.colorCord = list(pyautogui.position())
        print("Colour Select Button: ", self.colorCord)
        playsound.playsound("audio/ypop.wav")
    
    def set_input_area(self):
        self.inputCord = list(pyautogui.position())
        print("Input Text Area: ", self.inputCord)
        playsound.playsound("audio/ypop.wav")
    
    def set_close_button(self):
        self.closeCord = list(pyautogui.position())
        print("Close Button: ", self.closeCord)
        playsound.playsound("audio/ypop.wav")
    
    def save_and_exit(self, on_finish: callable = None):
        if not(self.is_config_valid()):
            print("You must set all coordinates before exiting!")
            playsound.playsound("audio/error.mp3")
            return False  # Indicate failure
        
        self.save_config(self.config_filename)
        playsound.playsound("audio/ding.mp3")
        
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
        except json.JSONDecodeError:
            print("Error decoding JSON from the configuration file.")
