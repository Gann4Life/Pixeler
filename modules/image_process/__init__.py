import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageFile, ImageGrab, UnidentifiedImageError
from playsound import playsound

class PixelExtractor:
    '''Extracts pixel data from an image.'''

    def __init__(self):
        self.image : ImageFile = None

    def get_color_at(self, x: int, y: int) -> str:
        '''Returns the hex color string at the given (x, y) coordinate.'''
        r, g, b, a = self.image.getpixel((x, y))
        return "#{:02x}{:02x}{:02x}".format(r, g, b)

    def get_pixels(self) -> list[str]:
        '''Returns a list of hex color strings for each pixel in the image.'''
        pixels = []

        for y in range(self.image.height):
            for x in range(self.image.width):
                r, g, b, a = self.image.getpixel((x, y))
                color = "#{:02x}{:02x}{:02x}".format(r, g, b)
                pixels.append(color)
        return pixels

    def load_image_file(self, file_path: str = None):
        '''Loads an image from a file path.'''
        root = tk.Tk()
        root.withdraw()
        if file_path == None:
            file_path = filedialog.askopenfilename()

        try:
            self.image = Image.open(file_path)
            self.try_convert_to_rgba()
            self.crop_resize()
            print(f"Loaded image: {file_path} ({self.image.width}x{self.image.height})")
        except UnidentifiedImageError as e:
            print("__ ERROR __")
            print("Unsupported file extension.")
            print(f'"{e}"')
            print("_"*8)
            playsound("audio/error.mp3")
        except PermissionError as e:
            print("__ ERROR __")
            print("Not enough permissions, please be careful.")
            print(f'"{e}"')
            print("_"*8)
            playsound("audio/error.mp3")


    def load_image_clipboard(self):
        '''Loads an image from the clipboard.'''

        try:
            clipboard_content = ImageGrab.grabclipboard()
            
            if isinstance(clipboard_content[0], str):
                self.load_image_file(clipboard_content[0])
                return

            self.image = clipboard_content
            if self.image is None:
                raise ValueError("No image found in clipboard.")    
            self.try_convert_to_rgba()
        except TypeError as type_error:
            print("__ ERROR __")
            print("Please copy an image to your clipboard.")
            print(f'"{type_error}"')
            print("_"*8)
            playsound("audio/error.mp3")
        except Exception as e:
            playsound("audio/error.mp3")
            raise e

    def resize(self, size=(32, 32)):
        '''Resizes the image to the given size.'''
        img = self.image.copy()
        img = img.resize(size)
        self.image = img

    def crop_resize(self, size=(32, 32)):
        '''Crops the image to fit 1:1 aspect ratio then resizes the image.'''
        width, height = self.image.size

        resize_to = min(width, height)

        left = (width - resize_to)/2
        top = (height - resize_to)/2
        right = (width + resize_to)/2
        bottom = (height + resize_to)/2

        self.image = self.image.crop((left, top, right, bottom))
        self.resize()

    def try_convert_to_rgba(self):
        '''Converts the image to RGBA mode.'''
        if self.image.mode != 'RGBA':
            self.image = self.image.convert('RGBA')