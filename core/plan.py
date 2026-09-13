'''Turns the processed GRID x GRID image into an ordered list of draw steps.

Colors are sorted by hex string (each color is picked once); the order of the
cells inside a color is chosen by a draw-order algorithm (core.order). The
default "horizontal" matches the original draw loop. Transparent pixels are
skipped.
'''
import random
from dataclasses import dataclass

from PIL import Image

from .order import order_cells, DEFAULT_METHOD


@dataclass(frozen=True)
class DrawStep:
    index: int
    color: str      # "#rrggbb"
    gx: int
    gy: int


def hex_of(r: int, g: int, b: int) -> str:
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def build_plan(img: Image.Image, method: str = DEFAULT_METHOD, seed: int = 0) -> list:
    '''img must be RGBA with binary alpha (see pipeline.process).'''
    if img is None:
        return []
    rng = random.Random(seed)
    px = img.load()
    by_color = {}
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            by_color.setdefault(hex_of(r, g, b), []).append((x, y))

    steps = []
    for color in sorted(by_color):
        for (x, y) in order_cells(method, by_color[color], max(img.width, img.height), rng):
            steps.append(DrawStep(len(steps), color, x, y))
    return steps


def color_boundaries(steps: list) -> list:
    '''Indices where a new color starts (useful as timeline ticks).'''
    out = []
    last = None
    for s in steps:
        if s.color != last:
            out.append(s.index)
            last = s.color
    return out


def render_progress(img: Image.Image, steps: list, upto: int) -> Image.Image:
    '''Image showing only the first `upto` steps placed; the rest is transparent.'''
    if img is None:
        return None
    out = Image.new('RGBA', img.size, (0, 0, 0, 0))
    src = img.load()
    dst = out.load()
    for s in steps[:max(0, upto)]:
        dst[s.gx, s.gy] = src[s.gx, s.gy]
    return out


def estimate_seconds(steps: list, frame_sleep: float) -> float:
    '''Rough ETA: each pixel costs ~4 clicks + one frame sleep; each color change ~3 settle-clicks.'''
    if not steps:
        return 0.0
    per_pixel = 0.003 + frame_sleep
    per_color = 3 * (2 * frame_sleep + 0.005) + 0.15   # + typing the hex code
    n_colors = len(color_boundaries(steps))
    return len(steps) * per_pixel + n_colors * per_color
