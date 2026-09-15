import json
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.calibration import CalibrationModel, GRID  # noqa: E402
from core.pipeline import NormRect, Adjustments, process  # noqa: E402
from core.plan import build_plan, render_progress, color_boundaries  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---- pipeline ---------------------------------------------------------------
def test_full_crop_box_and_size():
    r = NormRect()
    assert r.is_full()
    assert r.to_box(100, 50) == (0, 0, 100, 50)


def test_crop_box_never_empty():
    r = NormRect(0.5, 0.5, 0.0, 0.0)
    l, t, rr, b = r.to_box(10, 10)
    assert rr > l and b > t


def test_crop_survives_size_change():
    r = NormRect(0.25, 0.25, 0.5, 0.5)
    assert r.to_box(100, 100) == (25, 25, 75, 75)
    assert r.to_box(200, 400) == (50, 100, 150, 300)


def test_process_output_shape_and_binary_alpha():
    src = Image.new('RGBA', (64, 64), (255, 0, 0, 255))
    src.paste((0, 0, 0, 0), (0, 0, 32, 64))   # left half transparent
    out = process(src, NormRect(), Adjustments())
    assert out.size == (GRID, GRID) and out.mode == 'RGBA'
    assert set(out.getchannel('A').getdata()) <= {0, 255}
    assert out.getpixel((0, 0))[3] == 0
    assert out.getpixel((31, 0)) == (255, 0, 0, 255)


def test_crop_to_fit_uses_centered_square_never_stretches():
    # 120x40 image: left third red, middle third green, right third blue
    src = Image.new('RGBA', (120, 40), (255, 0, 0, 255))
    src.paste((0, 255, 0, 255), (40, 0, 80, 40))
    src.paste((0, 0, 255, 255), (80, 0, 120, 40))
    assert NormRect().to_square_box(120, 40) == (40, 0, 80, 40)
    out = process(src, NormRect(), Adjustments())
    assert {p[:3] for p in out.getdata()} == {(0, 255, 0)}          # only the middle square survives
    # a wide selection over the left two thirds -> its centered 40x40 square straddles red/green
    out = process(src, NormRect(0, 0, 2 / 3, 1), Adjustments())
    assert out.getpixel((0, 0))[:3] == (255, 0, 0) and out.getpixel((31, 0))[:3] == (0, 255, 0)


def test_palette_limit_reduces_colors():
    src = Image.effect_noise((64, 64), 128).convert('RGBA')
    out = process(src, NormRect(), Adjustments(palette_limit=4))
    colors = {p[:3] for p in out.getdata() if p[3]}
    assert len(colors) <= 4


# ---- plan ---------------------------------------------------------------------
def legacy_order(img):
    '''The ordering used by the old draw_loop in __main__.py.'''
    px = img.load()
    pixels = []
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            pixels.append("TRANSPARENT" if a == 0 else "#{:02x}{:02x}{:02x}".format(r, g, b))
    out = []
    for c in sorted(set(pixels)):
        if c == "TRANSPARENT":
            continue
        for y in range(img.height):
            for x in range(img.width):
                if pixels[y * img.width + x] == c:
                    out.append((c, x, y))
    return out


def test_plan_matches_legacy_order():
    img = Image.effect_noise((GRID, GRID), 200).convert('RGBA')
    img = process(img, NormRect(), Adjustments(palette_limit=6))
    steps = build_plan(img)
    assert [(s.color, s.gx, s.gy) for s in steps] == legacy_order(img)
    assert [s.index for s in steps] == list(range(len(steps)))


def test_render_progress_and_boundaries():
    img = Image.new('RGBA', (GRID, GRID), (10, 20, 30, 255))
    img.putpixel((0, 0), (200, 200, 200, 255))
    steps = build_plan(img)
    assert len(steps) == GRID * GRID
    assert color_boundaries(steps) == [0, GRID * GRID - 1]
    half = render_progress(img, steps, 10)
    assert sum(1 for p in half.getdata() if p[3]) == 10


# ---- calibration migration --------------------------------------------------------
def test_migration_from_legacy_config():
    with open(os.path.join(REPO, 'config.json')) as f:
        legacy = json.load(f)
    m = CalibrationModel()
    m.from_dict(legacy)
    assert m.area is not None
    assert m.fps == legacy["fps"]
    # centers derived from the square must stay close to the recorded ones
    for i in (0, 15, 31):
        assert abs(m.x[i] - legacy["x"][i]) <= 12
        assert abs(m.y[i] - legacy["y"][i]) <= 12
    d = m.to_dict()
    assert len(d["x"]) == GRID and len(d["y"]) == GRID and d["area"]


def test_cell_center_and_validity():
    m = CalibrationModel()
    m.area = (100.0, 200.0, 320.0)
    assert m.cell_center(0, 0) == (105, 205)
    assert m.cell_center(31, 31) == (415, 515)
    assert not m.is_config_valid()
    m.fps = 60
    m.colorCord, m.inputCord, m.closeCord = [1, 1], [2, 2], [3, 3]
    assert m.is_config_valid()


# ---- draw orders -------------------------------------------------------------------------
def _shape_image():
    '''Blue background, a red 10x10 square and a green blob (two parts).'''
    img = Image.new('RGBA', (GRID, GRID), (0, 0, 255, 255))
    img.paste((255, 0, 0, 255), (4, 4, 14, 14))
    img.paste((0, 255, 0, 255), (20, 20, 26, 26))
    img.paste((0, 255, 0, 255), (28, 2, 31, 6))
    img.paste((0, 0, 0, 0), (0, 28, 8, 32))          # a transparent corner
    return img


def test_every_method_is_a_permutation_with_grouped_colors():
    from core.order import method_keys
    img = _shape_image()
    reference = build_plan(img)
    for method in method_keys():
        steps = build_plan(img, method, seed=7)
        assert [s.index for s in steps] == list(range(len(reference)))
        assert sorted((s.color, s.gx, s.gy) for s in steps) == sorted((s.color, s.gx, s.gy) for s in reference)
        assert color_boundaries(steps) == color_boundaries(reference)      # colors stay contiguous, same order


def test_horizontal_is_legacy_and_scan_orders():
    img = _shape_image()
    assert build_plan(img, "horizontal") == build_plan(img)
    red = [(s.gx, s.gy) for s in build_plan(img, "vertical") if s.color == "#ff0000"]
    assert red[:3] == [(4, 4), (4, 5), (4, 6)]
    red = [(s.gx, s.gy) for s in build_plan(img, "diagonal") if s.color == "#ff0000"]
    assert red[:3] == [(4, 4), (5, 4), (4, 5)]
    blue = [(s.gx, s.gy) for s in build_plan(img, "spiral") if s.color == "#0000ff"]
    assert blue[:GRID] == [(x, 0) for x in range(GRID)] and blue[GRID] == (GRID - 1, 1)


def test_trace_draws_outline_before_inside():
    img = _shape_image()
    red = [(s.gx, s.gy) for s in build_plan(img, "trace") if s.color == "#ff0000"]
    outline = {(x, y) for (x, y) in red if x in (4, 13) or y in (4, 13)}
    assert set(red[:len(outline)]) == outline
    assert red[0] == (4, 4)
    # consecutive outline cells are neighbours (it walks the border, no hopping)
    for a, b in zip(red, red[1:len(outline)]):
        assert max(abs(a[0] - b[0]), abs(a[1] - b[1])) == 1
    green = [(s.gx, s.gy) for s in build_plan(img, "trace") if s.color == "#00ff00"]
    assert green[0][0] < 28           # biggest blob first


def test_maze_is_seeded_and_walks_neighbours():
    img = _shape_image()
    a = build_plan(img, "maze", seed=3)
    assert a == build_plan(img, "maze", seed=3)
    assert a != build_plan(img, "maze", seed=4)
    red = [(s.gx, s.gy) for s in a if s.color == "#ff0000"]
    adjacent = sum(1 for p, q in zip(red, red[1:]) if abs(p[0] - q[0]) + abs(p[1] - q[1]) == 1)
    assert adjacent >= 0.7 * (len(red) - 1)      # mostly a continuous path, some backtracking hops
    assert build_plan(img, "scatter", seed=1) != build_plan(img, "scatter", seed=2)


# ---- pencil strokes ----------------------------------------------------------------------------
class FakeAutoit:
    def __init__(self):
        self.log = []

    def mouse_move(self, x, y, speed=0):
        self.log.append(("move", x, y, speed))

    def mouse_down(self, b="left"):
        self.log.append(("down",))

    def mouse_up(self, b="left"):
        self.log.append(("up",))

    def mouse_click(self, *a):
        self.log.append(("click",))


def _pencil(monkeypatch, **pen_kwargs):
    import core.actuator as act
    from core.plan import DrawStep
    fake = FakeAutoit()
    monkeypatch.setattr(act, "autoit", fake)
    monkeypatch.setattr(act.time, "sleep", lambda *_: None)
    m = CalibrationModel()
    m.area, m.fps = (0.0, 0.0, 320.0), 60
    m.colorCord, m.inputCord, m.closeCord = [1, 1], [2, 2], [3, 3]
    picker = act.ColorPicker(m)
    monkeypatch.setattr(picker, "pick", lambda color: (fake.log.append(("pick", color)),
                                                        setattr(picker, "current_color", color)))
    pencil = act.PencilTool(m, picker, act.PenSettings(**pen_kwargs))
    return pencil, fake, DrawStep


def test_pen_holds_across_neighbours_and_lifts_on_jumps_and_colors(monkeypatch):
    pencil, fake, DrawStep = _pencil(monkeypatch)
    steps = [DrawStep(0, "#ff0000", 0, 0), DrawStep(1, "#ff0000", 1, 1), DrawStep(2, "#ff0000", 1, 2),
             DrawStep(3, "#ff0000", 10, 2),                     # jump
             DrawStep(4, "#00ff00", 10, 3)]                     # color change (adjacent, but must lift)
    for s in steps:
        pencil.draw_step(s)
    pencil.pen_up()
    kinds = [e[0] for e in fake.log]
    assert kinds.count("down") == 3 and kinds.count("up") == 3 and "click" not in kinds
    assert kinds.index("pick") < kinds.index("down")                     # color picked before the pen goes down
    # order: pick red, down, (moves), up, down (jump), up, pick green, down, up
    assert [k for k in kinds if k in ("pick", "down", "up")] == \
        ["pick", "down", "up", "down", "up", "pick", "down", "up"]
    assert all(e[3] == 0 for e in fake.log if e[0] == "move")           # teleport by default


def test_pen_legacy_clicks_and_glide(monkeypatch):
    pencil, fake, DrawStep = _pencil(monkeypatch, hold_stroke=False, interpolate=True, glide_steps=4)
    pencil.draw_step(DrawStep(0, "#ff0000", 0, 0))
    pencil.draw_step(DrawStep(1, "#ff0000", 1, 0))
    kinds = [e[0] for e in fake.log]
    assert kinds.count("click") == 8 and "down" not in kinds
    # AutoIt's own paced move is never used (it blocks for ~100 ms): every move is a teleport...
    assert all(e[3] == 0 for e in fake.log if e[0] == "move")
    # ...and a glide is our own hops between the two cell centres, ending on the target.
    clicks = [i for i, e in enumerate(fake.log) if e[0] == "click"]
    hops = [e[1:3] for e in fake.log[clicks[3] + 1:clicks[4]] if e[0] == "move"]
    assert len(hops) == 4 and hops[-1] == (15, 5)
    assert [x for x, _ in hops] == sorted(x for x, _ in hops) and all(5 < x <= 15 and y == 5 for x, y in hops)
    first = [e[1:3] for e in fake.log[:clicks[0]] if e[0] == "move"]
    assert first == [(5, 5)]                                           # nothing to glide from: teleport
    pencil.pen_up()                                                    # nothing held: no-op
    assert "up" not in [e[0] for e in fake.log]


def test_stroke_eta_counts_strokes():
    from core.actuator import PenSettings
    from core.plan import stroke_breaks, estimate_seconds
    img = _shape_image()
    steps = build_plan(img, "maze", seed=1)
    assert stroke_breaks(steps) < len(steps) / 5
    # a cell costs one frame in both modes; the pen delay (per stroke) is the only extra
    legacy = estimate_seconds(steps, 0.02, PenSettings(hold_stroke=False))
    held = estimate_seconds(steps, 0.02, PenSettings(pen_delay=0.0))
    assert abs(held - legacy) < 1e-9
    quick = held
    assert quick < estimate_seconds(steps, 0.02, PenSettings(pen_delay=0.2))      # pen delay is paid per stroke
    assert quick < estimate_seconds(steps, 0.02, PenSettings(pen_delay=0.0, color_delay=1.0))


PEN_MODES = (dict(hold_stroke=False), dict(hold_stroke=True), dict(hold_stroke=False, interpolate=True),
             dict(hold_stroke=True, interpolate=True))


def _clocked_pencil(monkeypatch, fps, speed=1.0):
    '''A PencilTool on a fake clock where every AutoIt primitive costs what it was measured to
    cost (scratchpad/bench_timing.py), so a mode that can't fit its work in a frame shows up
    as an overrun instead of passing by construction.'''
    import core.actuator as act
    clock = {"t": 0.0}
    monkeypatch.setattr(act.time, "perf_counter", lambda: clock["t"])
    monkeypatch.setattr(act.time, "sleep", lambda dt: clock.__setitem__("t", clock["t"] + max(0.0, dt)))
    m = CalibrationModel()
    m.area, m.fps, m.speed = (0.0, 0.0, 320.0), fps, speed
    m.colorCord, m.inputCord, m.closeCord = [1, 1], [2, 2], [3, 3]
    picker = act.ColorPicker(m)
    monkeypatch.setattr(picker, "pick", lambda color: setattr(picker, "current_color", color))

    class CostedAutoit(FakeAutoit):
        pen = None

        def mouse_move(self, x, y, speed=0):
            super().mouse_move(x, y, speed)
            clock["t"] += act.MOVE_COST

        def mouse_down(self, b="left"):
            super().mouse_down(b)
            clock["t"] += act.PRESS_COST

        def mouse_up(self, b="left"):
            super().mouse_up(b)
            clock["t"] += act.PRESS_COST

        def mouse_click(self, *a):
            super().mouse_click(*a)
            clock["t"] += self.pen.click_cost
    fake = CostedAutoit()
    monkeypatch.setattr(act, "autoit", fake)

    def make(**kw):
        pencil = act.PencilTool(m, picker, act.PenSettings(color_delay=0.0, **kw))
        fake.pen = pencil.pen
        picker.reset()
        return pencil
    return make, clock, m


def test_pen_modes_cost_one_frame_per_cell(monkeypatch):
    """Wall-clock parity: hold on/off and glide/teleport all take one frame per cell, at frame
    budgets that leave room for the work (24 ms and 15 ms)."""
    from core.plan import DrawStep
    row = [DrawStep(i, "#ff0000", i, 0) for i in range(10)] + [DrawStep(10, "#ff0000", 20, 0)]   # a stroke + a jump
    for fps in (50, 80):
        make, clock, m = _clocked_pencil(monkeypatch, fps)
        frame = m.get_frame_sleep_time()
        for kw in PEN_MODES:
            pencil = make(**kw)
            assert frame > pencil.cell_floor(), (fps, kw)
            t0 = clock["t"]
            for st in row:
                pencil.draw_step(st)
            # the only work outside a cell's stopwatch is the pen lift before a jump
            assert abs((clock["t"] - t0) - len(row) * frame) < 1e-3, (fps, kw)
            assert pencil.stats.cells == len(row) and pencil.stats.overruns == 0, (fps, kw)
            pencil.pen_up()


def test_pen_reports_overruns_below_floor(monkeypatch):
    """Speed pushed past what a cell physically costs: the pencil can't keep up, and says so."""
    from core.plan import DrawStep
    row = [DrawStep(i, "#ff0000", i, 0) for i in range(6)]
    make, clock, m = _clocked_pencil(monkeypatch, fps=240, speed=10.0)   # frame = 0.5 ms
    for kw in (dict(hold_stroke=False), dict(hold_stroke=True, interpolate=True, glide_steps=16)):
        pencil = make(**kw)
        assert m.get_frame_sleep_time() < pencil.cell_floor(), kw
        t0 = clock["t"]
        for st in row:
            pencil.draw_step(st)
        assert pencil.stats.overruns > 0 and "over budget" in pencil.stats.summary(), kw
        assert clock["t"] - t0 > len(row) * m.get_frame_sleep_time(), kw
        pencil.pen_up()
    # a glide sheds hops to fit a tight budget instead of blowing it: every move is still a teleport
    # and a cell mid-stroke (one move) never overruns, only the stroke start does
    assert pencil.stats.overruns == 1


def test_eta_never_promises_less_than_the_floor():
    from core.actuator import PenSettings
    from core.plan import estimate_breakdown
    steps = build_plan(_shape_image())
    pen = PenSettings(hold_stroke=False, color_delay=0.0)
    slow = estimate_breakdown(steps, 0.02, pen)
    capped = estimate_breakdown(steps, 0.0001, pen)
    assert not slow["capped"] and capped["capped"]
    assert abs(slow["cells"] - len(steps) * 0.02) < 1e-9
    assert abs(capped["cells"] - len(steps) * pen.cell_floor()) < 1e-9
    assert abs(slow["total"] - sum(slow[k] for k in ("cells", "colors", "strokes"))) < 1e-9
    assert PenSettings(hold_stroke=False).cell_floor() > PenSettings(hold_stroke=True).cell_floor()
    assert PenSettings(hold_stroke=False, click_hold=5).cell_floor() > PenSettings(hold_stroke=False, click_hold=1).cell_floor()
    assert PenSettings(interpolate=True, glide_steps=16).cell_floor() == PenSettings().cell_floor()   # hops are shed, not paid


def test_color_orders():
    from core.order import color_order_keys, order_colors, luminance
    import random
    img = _shape_image()
    reference = build_plan(img)
    counts = {}
    for s in reference:
        counts[s.color] = counts.get(s.color, 0) + 1
    for order in color_order_keys():
        steps = build_plan(img, "horizontal", seed=3, color_order=order)
        assert sorted((s.color, s.gx, s.gy) for s in steps) == sorted((s.color, s.gx, s.gy) for s in reference)
        assert len(color_boundaries(steps)) == len(counts)                  # each color picked once
    first = lambda order: [s.color for s in build_plan(img, color_order=order) if True][0]   # noqa: E731
    seq = lambda order: list(dict.fromkeys(s.color for s in build_plan(img, color_order=order, seed=3)))  # noqa: E731
    assert seq("hex") == sorted(counts) and seq("hex_desc") == sorted(counts)[::-1]
    lum = [luminance(c) for c in seq("dark_first")]
    assert lum == sorted(lum) and seq("light_first") == seq("dark_first")[::-1]
    big = [counts[c] for c in seq("big_first")]
    assert big == sorted(big, reverse=True) and seq("small_first")[0] == seq("big_first")[-1]
    assert seq("rainbow")[0] == "#ff0000"                                  # red before green before blue
    assert seq("random") == seq("random") and seq("random") != order_colors("random", counts, random.Random(99))


def test_dither_and_invert():
    from core.pipeline import Adjustments, process, NormRect
    grad = Image.linear_gradient("L").convert("RGBA")                      # 256x256 vertical ramp
    plain = process(grad, NormRect(), Adjustments(palette_limit=4))
    dith = process(grad, NormRect(), Adjustments(palette_limit=4, dither=True))
    assert plain.tobytes() != dith.tobytes()                                # dither actually changes pixels
    assert len(set(dith.getdata())) <= 4                                    # ...within the palette
    inv = process(grad, NormRect(), Adjustments(invert=True))
    top, bottom = inv.getpixel((0, 0)), inv.getpixel((0, GRID - 1))
    assert top[0] > 200 and bottom[0] < 60                                  # ramp flipped
