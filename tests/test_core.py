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
