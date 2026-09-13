'''Draw-order algorithms: how the cells of one color are sequenced.

Pixeler clicks every cell, so unlike stroke-based tools (autodraw's DFS /
edge-following) an algorithm never changes *what* is drawn — only the order in
which the picture appears. Colors stay grouped (a color switch costs three
settle-clicks and typing a hex code); the algorithm runs once per color.

Every function takes the cells of one color as (x, y) tuples and returns the
same cells reordered. Randomized methods take a `random.Random` so a seed
reproduces the plan exactly.'''
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


def method_keys() -> list:
    return [m[0] for m in METHODS]


def is_random(method: str) -> bool:
    return method in RANDOM_METHODS


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
