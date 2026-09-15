# Pixeler

Draws pixel art for you in Roblox *Starving Artists*: load an image, crop and
tweak it in two small floating panels that stay on top of the game, press
Play, and Pixeler clicks every pixel on the 32×32 canvas.

## Prerequisites

* Python 3.10, from [python.org](https://www.python.org/downloads/) (tick *Add to PATH*), or:

```powershell
winget install --id Python.Python.3.10
```

## Install

Download the [zip](https://github.com/Gann4Life/Pixeler/archive/refs/heads/main.zip) and extract it, or:

```bash
git clone https://github.com/Gann4Life/Pixeler
```

Run `start.bat`. The first run creates a virtual environment in `.venv` and
installs the requirements (PySide6, Pillow, keyboard, PyAutoIt, playsound);
afterwards it just starts the app.

Roblox must run **windowed or borderless** (not exclusive fullscreen) so the
panels can stay on top of it.

## The panels

Both panels are frameless, always on top, draggable by their title bar and
resizable from any edge or corner. **⋮** opens per-panel options (opacity,
always-on-top, reset position, show the other panel, hide this panel, quit).
**✕** quits Pixeler. `Ctrl+Shift+H` hides/shows both panels. Both panels are
always shown on startup. Positions, sizes and opacity are remembered in
`ui_state.json`.

### Input

* Shows the source image. Drag the handles to crop; **Shift** keeps the
  aspect ratio, **Alt** resizes symmetrically; drag inside to move; drag on
  the empty area to start a new crop. **⟲ crop** resets to the whole image.
  Mouse wheel zooms, middle/right-drag pans, middle double-click (or `0`)
  fits the image again.
  The crop is kept when you load another image. The canvas is square, so the
  centered square of your selection is what gets drawn (dashed outline) — the
  image is never stretched.
* **▶ / ⏸** play or pause, **⏹** stop. **📁** load a file, **📋** paste from the
  clipboard. **− + ⊡** zoom the view.
* Play (and resume) is *armed*: Pixeler waits until no key is held, then waits
  the **start delay** (Settings, default 1.5 s) before the first click — so the
  hotkey that started it can never leak into the game.
* The timeline slider scrubs through every pixel that will be drawn. Pause,
  drag it anywhere, press Play — drawing resumes from there.
* **⚙** opens Settings (FPS, hotkeys, calibration).

### Status

A small third panel with two lines: what Pixeler is doing (image loaded,
starting countdown, step progress, errors) and a hint with the hotkeys that
make sense right now.

### Output

* Preview of the processed 32×32 result.
* Palette limit, dither (only visible with a limited palette), invert colors
  (negative), brightness, contrast, saturation, gamma and alpha cutoff — every
  change updates the preview instantly.
* **Draw order** — how the pixels of each color are sequenced (colors are
  always drawn one after another, since switching costs a color picker trip):
  *Horizontal* / *Vertical* (printer scans), *Diagonal*, *Spiral* (outer ring
  inwards), *Trace* (outline of each shape first, then the inside, like a
  robot tracing), *Maze* (starts at a random cell and carves a winding path,
  backtracking when stuck) and *Scatter* (random). 🎲 rerolls the random ones.
  Scrub the timeline to watch any order play out in the preview.
* **Color order** — in which order the colors are picked: hex code (the
  classic) or reversed, dark → light, light → dark, biggest area first,
  smallest area first, rainbow (grays, then by hue) and random (🎲).
* **Speed** — multiplier on the wait between inputs (the base comes from the
  FPS in Settings). Applies to every pen mode. Can be changed while drawing;
  the ETA follows it. A cell can't be faster than the inputs it physically
  needs (~1 ms held, ~6 ms click-per-cell): past that point the status line
  turns orange and says **Speed capped**, and pushing the slider further
  changes nothing.
* **Show final result** on: preview the finished picture. Off: only the pixels
  placed so far are shown, following the timeline. Click-dragging the timeline
  always previews the progress, whatever the toggle says.
* The status line shows how many colors (= color picker trips), steps and
  roughly how long the drawing will take; hover it for the breakdown (cells,
  color changes, stroke delays). When a draw finishes the console prints
  `[timing] … ms/cell avg … over budget` so you can see what it really cost.

### Pen (⚙ Settings)

Every cell costs exactly one frame (1.2 / FPS ÷ Speed) in every mode; the
options below only change *how* the cursor gets there.

* **Hold the button across neighbouring cells** (default on): the pen goes
  down on the first cell of a stroke and stays down while the next step
  touches the current cell in any of the 8 directions. A jump or a color
  change lifts it. Off = the original click-per-cell. A stroke start presses
  at the end of its frame, exactly where the click of the original mode lands,
  so both modes draw at the same rate.
* **Pen up/down delay** (default 0) and **Color change delay**: extra waits,
  paid per stroke / per color, never per cell.
* **Interpolate movement** (default off): walk the cursor between cells in
  **Glide steps** (default 4) instant hops instead of one teleport. The hops
  are spread evenly across the cell's frame, so a glided cell costs exactly
  one frame like any other and follows the Speed slider; when the frame is
  too short for that many hops, hops are dropped rather than time added. A
  diagonal glide crosses the corner shared by four cells, so the game can
  paint a stray neighbour — keep it off for pixel-perfect results.
* **Click hold** (default 1 ms): how long the button stays down inside a
  click in click-per-cell mode. AutoIt's stock 10 + 10 ms per click is what
  used to pin that mode at ~80 ms per cell regardless of Speed.
* Pause and Stop always lift the pen.

## Hotkeys

Global — they work while Roblox has focus — and built on `Ctrl+Shift` so they
never type into chat, on keys Roblox ignores (Space would make your avatar
jump, I/O zoom the camera). All rebindable in **⚙ Settings**, which warns if
you pick a key the game reacts to.

| Action | Default |
|---|---|
| Play / Pause | `Ctrl+Shift+P` |
| Stop | `Ctrl+Shift+X` |
| Load image file | `Ctrl+Shift+L` |
| Load from clipboard | `Ctrl+Shift+V` |
| Reset crop | `Ctrl+Shift+R` |
| Show / hide panels | `Ctrl+Shift+H` |

## Calibration

Open the drawing panel in Starving Artists, then **⚙ → Calibrate**. A
translucent overlay covers the screen:

1. Drag a square over the game's canvas. It is always square and shows a red
   dot where every one of the 32×32 pixels will be clicked. Fine-tune it with
   the corner/edge handles, drag it to move it, or nudge with the arrow keys
   (Shift = 10 px).
2. Drag the three crosshair markers onto the **color button**, its **hex
   input** field and its **close button**.
3. **Test** moves the mouse over the corners and the markers so you can check
   them; **Save** (Enter) writes `config.json`. Esc cancels.

Set your average Roblox FPS in Settings (Shift+F5 in Roblox shows it) — inputs
are spaced to about 1.2 frames so the game registers every click.

An old `config.json` from the click-64-pixels era is migrated automatically;
the overlay opens pre-filled so you only need to adjust.

## Development

```
.venv\Scripts\python.exe -m pytest tests
```

Design notes: [docs/ui-rework.md](docs/ui-rework.md),
[docs/calibration-overlay.md](docs/calibration-overlay.md).
