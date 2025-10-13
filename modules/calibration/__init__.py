import time
import pyautogui
import keyboard
import playsound
import json

class ScreenCalibration:
    def __init__(self):
        self.x = []
        self.y = []
        self.colorCord = [0, 0]
        self.inputCord = [0, 0]
        self.closeCord = [0, 0]
    
    def run(self, on_finish: callable = None):
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
        if len(self.x) != 32 or len(self.y) != 32 or self.colorCord == [0, 0] or self.inputCord == [0, 0] or self.closeCord == [0, 0]:
            print("You must set all coordinates before exiting!")
            playsound.playsound("audio/error.mp3")
            return False  # Indicate failure
        
        config_data = {
            "x": self.x,
            "y": self.y,
            "colorCord": self.colorCord,
            "inputCord": self.inputCord,
            "closeCord": self.closeCord,
        }
        
        with open('config.json', 'w+') as config_file:
            json.dump(config_data, config_file, indent=4)
        
        print("Configuration saved to config.json.")
        playsound.playsound("audio/ding.mp3")
        
        keyboard.unhook_all()  # Clean up keyboard listeners
        
        if on_finish:
            on_finish()
        
        return True  # Indicate success
