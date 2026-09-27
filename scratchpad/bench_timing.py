'''Scratch benchmark: the real cost of every autoit primitive Pixeler uses.

Why: core/actuator.py budgets one frame per cell and sleeps only the remainder
(`_wait_frame`). That only paces anything while the work inside the budget is
cheaper than the frame. This measures the actual floor per primitive so we know
where each draw mode saturates and the Speed slider stops doing anything.

Moves the real cursor inside a small safe box and clicks there a few hundred
times. Nothing here is imported by the app; delete it when done.

    .venv/Scripts/python scratchpad/bench_timing.py
'''
import contextlib
import ctypes
import statistics
import time

import autoit

SAFE = (400, 400)       # a spot with nothing destructive under it
CELL_PX = 13            # ~one 32x32 cell on a 420 px canvas
COUNTDOWN = 5


# ---- harness --------------------------------------------------------------
def timer_resolution(ms):
    '''Same 1 ms scheduler tick core/drawer.py asks for while drawing.'''
    with contextlib.suppress(Exception):
        winmm = ctypes.windll.winmm
        (winmm.timeBeginPeriod if ms else winmm.timeEndPeriod)(ms or 1)


def bench(label, fn, n=200):
    fn()                                         # warm up the DLL
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        ts.append((time.perf_counter() - t0) * 1000)
    ts.sort()
    med = statistics.median(ts)
    print(f"  {label:<32} min {ts[0]:7.3f}  med {med:7.3f}  p95 {ts[int(n * 0.95)]:7.3f}  ms")
    return med


def set_click_delays(click, down):
    autoit.auto_it_set_option("MouseClickDelay", click)
    autoit.auto_it_set_option("MouseClickDownDelay", down)


# ---- measurements ---------------------------------------------------------
def measure_sleep():
    '''How small a sleep can we actually ask for? This bounds the frame budget.'''
    print("\n[sleep granularity]")
    out = {}
    for res in (None, 1):
        timer_resolution(res)
        for want in (0.001, 0.002, 0.005):
            ts = []
            for _ in range(60):
                t0 = time.perf_counter()
                time.sleep(want)
                ts.append((time.perf_counter() - t0) * 1000)
            tag = "timeBeginPeriod(1)" if res else "default tick"
            out[(res, want)] = statistics.median(ts)
            print(f"  sleep({want * 1000:.0f}ms) {tag:<20} -> med {statistics.median(ts):7.3f} ms")
        timer_resolution(None)
    return out


def measure_mouse():
    x, y = SAFE
    flip = [0]
    res = {}

    print("\n[moves]")

    def move0():
        flip[0] ^= 1
        autoit.mouse_move(x + flip[0] * CELL_PX, y, 0)

    res["move0"] = bench(f"mouse_move(speed=0) {CELL_PX}px", move0)

    def move0_far():
        flip[0] ^= 1
        autoit.mouse_move(x + flip[0] * 300, y, 0)

    res["move0_far"] = bench("mouse_move(speed=0) 300px", move0_far)

    print("\n[button down/up  (AU3_MouseDown/Up - no click delays)]")

    def downup():
        autoit.mouse_down("left")
        autoit.mouse_up("left")

    res["downup"] = bench("mouse_down + mouse_up", downup)

    print("\n[clicks  (AU3_MouseClick - honours the delay options)]")
    for d in (10, 5, 2, 1, 0):
        set_click_delays(d, d)
        res[f"click_{d}"] = bench(f"mouse_click  delays {d}/{d}", autoit.mouse_click, 60)
    set_click_delays(10, 10)

    print("\n[glide  (AU3_MouseMove with a speed - paced inside the DLL)]")
    for g in (1, 2, 3, 5, 10, 20):
        flip[0] = 0

        def glide(g=g):
            flip[0] ^= 1
            autoit.mouse_move(x + flip[0] * CELL_PX, y, g)

        res[f"glide_{g}"] = bench(f"mouse_move(glide={g}) {CELL_PX}px", glide, 40)
    return res


# ---- what it means --------------------------------------------------------
def report(m):
    move, click10, click0, downup = m["move0"], m["click_10"], m["click_0"], m["downup"]
    print("\n" + "=" * 74)
    print("PER-CELL FLOOR (work that must happen inside the frame budget)")
    print("=" * 74)

    modes = {
        "HOLD on, stroke continues (teleport)": move,
        "HOLD on, stroke start (teleport)": 4 * move + 2 + downup,
        "HOLD off / draw_at, click delays 10/10": 4 * move + 4 * click10 + 2,
        "HOLD off / draw_at, click delays 0/0": 4 * move + 4 * click0 + 2,
        "HOLD on, continues (glide=5)": m["glide_5"],
        "HOLD on, continues (glide=1)": m["glide_1"],
    }
    for label, floor in modes.items():
        print(f"  {label:<42} {floor:7.2f} ms")

    print("\n" + "=" * 74)
    print("WHERE THE SPEED SLIDER SATURATES   (speed >= 1.2 / (fps * floor))")
    print("=" * 74)
    print(f"  {'mode':<42} {'60fps':>9} {'120fps':>9} {'240fps':>9}")
    for label, floor in modes.items():
        cells = []
        for fps in (60, 120, 240):
            sat = 1.2 / (fps * (floor / 1000.0))
            cells.append("never" if sat >= 4.0 else (f"{sat:.2f}x" if sat >= 0.25 else "ALWAYS"))
        print(f"  {label:<42} {cells[0]:>9} {cells[1]:>9} {cells[2]:>9}")
    print("\n  'never'  = Speed works across the whole 0.25-4.0 slider")
    print("  '1.40x'  = Speed does nothing above 1.40x")
    print("  'ALWAYS' = saturated at every slider position; Speed is inert")

    print("\n  Colour change adds 3 settle-clicks: "
          f"{3 * (3 * move + click10):.1f} ms at 10/10 -> {3 * (3 * move + click0):.1f} ms at 0/0")


def main():
    print(__doc__.split("\n\n")[0])
    print(f"\nClicking ~{4 * 60 + 200} times at {SAFE}. Make sure nothing destructive is under there.")
    for i in range(COUNTDOWN, 0, -1):
        print(f"  starting in {i}...  hands off the mouse")
        time.sleep(1)
    start = autoit.mouse_get_pos()
    timer_resolution(1)
    try:
        measure_sleep()
        m = measure_mouse()
        report(m)
    finally:
        timer_resolution(None)
        set_click_delays(10, 10)
        autoit.mouse_move(start[0], start[1], 0)
        print("\ndone; cursor restored, autoit options back to defaults")


if __name__ == "__main__":
    main()
