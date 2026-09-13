'''Turns the processed GRID x GRID image into an ordered list of draw steps.

Each color is picked once; the order of the colors and the order of the cells
inside a color are chosen by the algorithms in core.order. The defaults (hex
order, "horizontal") match the original draw loop. Transparent pixels are
skipped.
'''
import random
from dataclasses import dataclass

from PIL import Image

from .order import order_cells, order_colors, DEFAULT_METHOD, DEFAULT_COLOR_ORDER


@dataclass(frozen=True)
class DrawStep:
    index: int
    color: str      # "#rrggbb"
    gx: int
    gy: int


def hex_of(r: int, g: int, b: int) -> str:
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def build_plan(img: Image.Image, method: str = DEFAULT_METHOD, seed: int = 0,
               color_order: str = DEFAULT_COLOR_ORDER) -> list:
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
    for color in order_colors(color_order, by_color, rng):
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


def stroke_breaks(steps: list) -> int:
    '''Number of strokes when the pen is held across touching cells of the same color.'''
    n = 0
    last = None
    for s in steps:
        if last is None or s.color != last.color or max(abs(s.gx - last.gx), abs(s.gy - last.gy)) > 1:
            n += 1
        last = s
    return n


def estimate_seconds(steps: list, frame_sleep: float, pen=None) -> float:
    '''Rough ETA. One frame per cell in every mode; each color change ~3 settle-clicks + typing.
    With a held pen (`pen.hold_stroke`) each stroke adds the pen delay twice (down and up).'''
    if not steps:
        return 0.0
    n_colors = len(color_boundaries(steps))
    per_color = 3 * (2 * frame_sleep + 0.005) + 0.15   # + typing the hex code
    if pen is not None:
        per_color += pen.color_delay
    total = len(steps) * frame_sleep + n_colors * per_color
    if pen is not None and pen.hold_stroke:
        total += stroke_breaks(steps) * 2 * pen.pen_delay
    return total
