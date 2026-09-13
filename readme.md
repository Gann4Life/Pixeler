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
* Palette limit, dither, brightness, contrast, saturation, gamma and alpha
  cutoff — every change updates the preview instantly.
* **Draw order** — how the pixels of each color are sequenced (colors are
  always drawn one after another, since switching costs a color picker trip):
  *Horizontal* / *Vertical* (printer scans), *Diagonal*, *Spiral* (outer ring
  inwards), *Trace* (outline of each shape first, then the inside, like a
  robot tracing), *Maze* (starts at a random cell and carves a winding path,
  backtracking when stuck) and *Scatter* (random). 🎲 rerolls the random ones.
  Scrub the timeline to watch any order play out in the preview.
* **Show final result** on: preview the finished picture. Off: only the pixels
  placed so far are shown, following the timeline. Click-dragging the timeline
  always previews the progress, whatever the toggle says.
* The status line shows how many colors (= color picker trips), steps and
  roughly how long the drawing will take.

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
