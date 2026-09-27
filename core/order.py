'''Draw-order algorithms: in which order the colors are picked, and how the
cells of one color are sequenced.

Pixeler clicks every cell, so unlike stroke-based tools (autodraw's DFS /
edge-following) an algorithm never changes *what* is drawn — only the order in
which the picture appears. Colors stay grouped (a color switch costs three
settle-clicks and typing a hex code); the algorithm runs once per color.

Every function takes the cells of one color as (x, y) tuples and returns the
same cells reordered. Randomized methods take a `random.Random` so a seed
reproduces the plan exactly.'''
import colorsys
import functools
import random

DIRS4 = ((1, 0), (0, 1), (-1, 0), (0, -1))
DIRS8 = DIRS4 + ((1, 1), (-1, 1), (-1, -1), (1, -1))

# (key, label, description). Order = order in the UI.
METHODS = (
    ("horizontal", "Horizontal (printer)",
     "Row by row, left to right. The classic order."),
    ("vertical", "Vertical (printer)",
     "Column by column, top to bottom."),
    ("diagonal", "Diagonal",
     "Sweeps diagonal lines from the top-left corner to the bottom-right."),
    ("spiral", "Spiral",
     "Clockwise from the outer ring of the canvas inwards."),
    ("trace", "Trace (outline, then fill)",
     "For each shape: walk its outline first, then fill the inside, like a robot tracing. "
     "Biggest shapes first."),
    ("maze", "Maze",
     "Starts at a random cell of each color and carves a winding path through the shape, "
     "backtracking when stuck (randomized depth-first search). Press 🎲 for another maze."),
    ("scatter", "Scatter",
     "Random order. Press 🎲 to reshuffle."),
)
DEFAULT_METHOD = "horizontal"
RANDOM_METHODS = ("maze", "scatter")
STRAIGHT_BIAS = 0.65   # maze: chance to keep going straight when possible (longer corridors)


# (key, label, description) for the order in which the colors are picked.
COLOR_ORDERS = (
    ("hex", "Hex code (A→Z)",
     "Colors sorted by their hex code. The classic order."),
    ("hex_desc", "Hex code (Z→A)",
     "The classic order, reversed."),
    ("dark_first", "Dark → light",
     "Darkest color first, brightest last (shadows before highlights)."),
    ("light_first", "Light → dark",
     "Brightest color first, darkest last."),
    ("big_first", "Biggest area first",
     "The color with the most pixels first, so the picture takes shape early."),
    ("small_first", "Smallest area first",
     "Details first, big areas last."),
    ("rainbow", "Rainbow",
     "Grays first (dark to light), then by hue: red, yellow, green, cyan, blue, magenta."),
    ("random", "Random",
     "Shuffled. Press 🎲 to reshuffle."),
)
DEFAULT_COLOR_ORDER = "hex"
RANDOM_COLOR_ORDERS = ("random",)


def method_keys() -> list:
    return [m[0] for m in METHODS]


def color_order_keys() -> list:
    return [m[0] for m in COLOR_ORDERS]


def is_random(method: str, color_order: str = DEFAULT_COLOR_ORDER) -> bool:
    '''True when the 🎲 seed affects the plan.'''
    return method in RANDOM_METHODS or color_order in RANDOM_COLOR_ORDERS


# ---- color order -----------------------------------------------------------------------------
def _rgb(color: str) -> tuple:
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def luminance(color: str) -> float:
    r, g, b = _rgb(color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _rainbow_key(color: str) -> tuple:
    r, g, b = _rgb(color)
    h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if s < 0.12:                                  # near-gray: before the hues, dark to light
        return (0, v, 0.0)
    return (1, h, v)


def order_colors(order: str, by_color: dict, rng: random.Random) -> list:
    '''Sequence of the color keys of `by_color` ({"#rrggbb": [cells]}). Ties fall back to the
    hex order so the result is deterministic.'''
    colors = sorted(by_color)
    if order == "hex_desc":
        return colors[::-1]
    if order == "dark_first":
        return sorted(colors, key=lambda c: (luminance(c), c))
    if order == "light_first":
        return sorted(colors, key=lambda c: (-luminance(c), c))
    if order == "big_first":
        return sorted(colors, key=lambda c: (-len(by_color[c]), c))
    if order == "small_first":
        return sorted(colors, key=lambda c: (len(by_color[c]), c))
    if order == "rainbow":
        return sorted(colors, key=lambda c: (_rainbow_key(c), c))
    if order == "random":
        rng.shuffle(colors)
        return colors
    return colors


def order_cells(method: str, cells: list, grid: int, rng: random.Random) -> list:
    if not cells:
        return []
    fn = _ALGORITHMS.get(method, _horizontal)
    return fn(list(cells), grid, rng)


# ---- scan orders ---------------------------------------------------------------------------
def _horizontal(cells, grid, rng):
    return sorted(cells, key=lambda c: (c[1], c[0]))


def _vertical(cells, grid, rng):
    return sorted(cells, key=lambda c: (c[0], c[1]))


def _diagonal(cells, grid, rng):
    return sorted(cells, key=lambda c: (c[0] + c[1], c[1]))


@functools.lru_cache(maxsize=4)
def _spiral_rank(n: int) -> dict:
    '''Rank of every grid cell along a clockwise inward spiral starting top-left.'''
    rank, k = {}, 0
    top, left, bottom, right = 0, 0, n - 1, n - 1
    while top <= bottom and left <= right:
        for x in range(left, right + 1):
            rank[(x, top)] = k
            k += 1
        for y in range(top + 1, bottom + 1):
            rank[(right, y)] = k
            k += 1
        if top < bottom:
            for x in range(right - 1, left - 1, -1):
                rank[(x, bottom)] = k
                k += 1
        if left < right:
            for y in range(bottom - 1, top, -1):
                rank[(left, y)] = k
                k += 1
        top, left, bottom, right = top + 1, left + 1, bottom - 1, right - 1
    return rank


def _spiral(cells, grid, rng):
    rank = _spiral_rank(grid)
    return sorted(cells, key=lambda c: rank.get(c, 0))


def _scatter(cells, grid, rng):
    cells = sorted(cells)      # deterministic input for the seed
    rng.shuffle(cells)
    return cells


# ---- trace: outline first, then the inside, per connected shape --------------------------
def components(cells) -> list:
    '''8-connected components, biggest first (what autodraw calls "chunks").'''
    todo = set(cells)
    out = []
    for seed in sorted(cells):
        if seed not in todo:
            continue
        comp, stack = [], [seed]
        todo.discard(seed)
        while stack:
            x, y = stack.pop()
            comp.append((x, y))
            for dx, dy in DIRS8:
                p = (x + dx, y + dy)
                if p in todo:
                    todo.discard(p)
                    stack.append(p)
        out.append(comp)
    out.sort(key=len, reverse=True)
    return out


def _preference(d):
    '''Directions to try from heading d: straight, left, right, back, then the rest.'''
    dx, dy = d
    first = [d, (-dy, dx), (dy, -dx), (-dx, -dy)]
    return first + [e for e in DIRS8 if e not in first]


def _walk(cells, start, heading=(1, 0)) -> list:
    '''Greedy walk: keep heading if possible, else turn, else hop to the nearest unvisited cell.
    On a one-cell-thick outline this behaves like a wall follower.'''
    todo = set(cells)
    cur = start
    todo.discard(cur)
    out = [cur]
    d = heading
    while todo:
        nxt = None
        for cand in _preference(d):
            p = (cur[0] + cand[0], cur[1] + cand[1])
            if p in todo:
                nxt, d = p, cand
                break
        if nxt is None:
            nxt = min(todo, key=lambda c: ((c[0] - cur[0]) ** 2 + (c[1] - cur[1]) ** 2, c[1], c[0]))
            d = (_sign(nxt[0] - cur[0]), _sign(nxt[1] - cur[1]))
            if d == (0, 0):
                d = (1, 0)
        todo.discard(nxt)
        out.append(nxt)
        cur = nxt
    return out


def _sign(v):
    return (v > 0) - (v < 0)


def _trace(cells, grid, rng):
    filled = set(cells)
    out = []
    for comp in components(cells):
        comp_set = set(comp)
        edge = [c for c in comp
                if any((c[0] + dx, c[1] + dy) not in filled for dx, dy in DIRS4)]
        edge_set = set(edge)
        inner = [c for c in comp if c not in edge_set]
        start = min(edge, key=lambda c: (c[1], c[0]))     # top-left-most outline cell
        out += _walk(edge, start)
        if inner:
            last = out[-1]
            start = min(inner, key=lambda c: ((c[0] - last[0]) ** 2 + (c[1] - last[1]) ** 2, c[1], c[0]))
            out += _walk(inner, start)
        assert len(comp_set) == len(edge) + len(inner)
    return out


# ---- maze: randomized depth-first search with a straight bias ------------------------------
def _maze(cells, grid, rng):
    todo = set(cells)
    out = []
    while todo:                                   # one pass per connected region
        start = rng.choice(sorted(todo))
        todo.discard(start)
        out.append(start)
        stack = [(start, None)]
        while stack:
            cur, d = stack[-1]
            options = [e for e in DIRS4 if (cur[0] + e[0], cur[1] + e[1]) in todo]
            if not options:
                stack.pop()                       # dead end: back up to the last fork
                continue
            step = d if (d in options and rng.random() < STRAIGHT_BIAS) else rng.choice(options)
            p = (cur[0] + step[0], cur[1] + step[1])
            todo.discard(p)
            out.append(p)
            stack.append((p, step))
    return out


_ALGORITHMS = {
    "horizontal": _horizontal,
    "vertical": _vertical,
    "diagonal": _diagonal,
    "spiral": _spiral,
    "trace": _trace,
    "maze": _maze,
    "scatter": _scatter,
}
