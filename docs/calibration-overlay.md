# Calibration overlay — design

## Problem

Calibration today is a console wizard: the user clicks the 32 pixels of the
top row, then the 32 pixels of the left column, one by one, and Pixeler
extrapolates a grid from those 64 clicks. It is slow, error-prone (one
mis-click shifts every pixel after it) and has to be redone every time the
game window moves.

## Goal

Define the drawing area with **one mouse drag**, fine-tune it with **visible
drag handles**, and see immediately where every pixel will land.

## Model

```
CalibrationModel
  area           = (x0, y0, size)   # square, physical screen pixels
  color_button   = (x, y)           # opens the game's color picker
  hex_input      = (x, y)           # the picker's hex text field
  close_button   = (x, y)           # the picker's close button
  fps            = int              # used to derive the per-input sleep time

  cell_center(gx, gy) = (x0 + (gx + 0.5) * size / 32,
                         y0 + (gy + 0.5) * size / 32)
```

`config.json` keeps its existing keys (`x`, `y`, `colorCord`, `inputCord`,
`closeCord`, `fps`) and gains `area`. On load, if `area` is missing but `x`
and `y` have 32 entries each, the square is derived from them
(`cell = (x[31] - x[0]) / 31`, `x0 = x[0] - cell / 2`, `size = 32 * cell`,
averaged with the vertical estimate). On save, `x` and `y` are regenerated
from `area` so the file stays readable by older tooling.

## The overlay window

* Fullscreen on the monitor under the mouse cursor.
* Frameless, always on top, tool window (no taskbar entry).
* Translucent background with a 25 % black tint — the game remains visible
  underneath.
* `Esc` cancels, `Enter` saves. A small toolbar at the top-center shows the
  current step's hint plus **Save**, **Cancel** and **Test** buttons.
  *Test* moves the mouse (no clicks) to the four corner cells and to the three
  button markers so the user can eyeball the result.

### Step A — canvas area

1. Press and drag anywhere. A square grows from the press point; its side is
   `max(|dx|, |dy|)`, so it is always 1:1. The direction of the drag decides
   which way it grows.
2. While dragging, a 32×32 grid is drawn inside the square with a **red dot at
   the center of every cell** (1024 dots; drawn with `QPainter.drawPoints`).
3. On release the square becomes editable:
   * 4 **corner handles** — resize with the opposite corner anchored; the
     square constraint is enforced by taking the larger of the two deltas.
   * 4 **edge handles** — move that side; the two perpendicular sides move
     symmetrically so the shape stays square around the same center line.
   * Dragging inside the square moves it.
   * Arrow keys nudge by 1 px, `Shift`+arrows by 10 px.
   * Handles are visible filled squares (shared with the crop editor).
4. The result is stored as `area`.

### Step B — color picker buttons

The game's color picker still has to be driven, so its three positions still
need to be known. They are shown as three draggable crosshair markers,
labelled *Color button*, *Hex input* and *Close button*, pre-placed from the
previous config (or stacked beside the canvas if none). Drag each onto the
matching game button. Clicking a marker focuses it for arrow-key nudging.

### Save

Writes `config.json` through the same safe-save rule as today: refuse (and
play the error sound) if anything is unset. If an old-style config exists the
overlay opens pre-populated from the migrated square, so upgrading users only
have to adjust.

## Out of scope (v1)

* Auto-detecting the canvas from a screenshot.
* Grid sizes other than 32×32 (`GRID` is a single constant in
  `core/calibration.py`).
