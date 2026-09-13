# UI rework — design

Pixeler is rebuilt around two small floating panels that stay on top of the
game, so you can load, crop, tweak and draw without leaving Roblox.

## Framework

**PySide6 (Qt 6).** It gives us multiple independent frameless always-on-top
windows, per-window opacity, a translucent fullscreen overlay for
calibration, a graphics view for drag handles, tooltips, sliders and a
thread→UI signal system. Kivy is single-window and touch-oriented; tkinter
can't do the overlay cleanly.

`QT_ENABLE_HIGHDPI_SCALING=0` is set before the app starts so Qt coordinates
equal the physical screen coordinates that `autoit` uses.

## Layout

```
__main__.py            bootstrap, wiring
core/                  UI-independent
  pipeline.py          source → crop → 32×32 → adjustments → palette
  plan.py              output image → ordered DrawStep list, progress render
  drawer.py            worker thread, play(from)/pause/stop, progress signal
  calibration.py       CalibrationModel, config.json load/save/migration
  actuator.py          ColorPicker + PencilTool (autoit)
  hotkeys.py           global hotkeys via `keyboard`, rebindable
  state.py             ui_state.json (panel geometry/opacity, crop, adjustments, hotkeys)
  audio.py             sound effects
ui/
  floating_panel.py    base panel: drag, resize, ⋮ opacity menu, persistence
  input_panel.py       image, crop editor, transport, timeline, load buttons, ⚙
  crop_editor.py       crop rect with 8 handles; Shift = aspect, Alt = symmetric
  output_panel.py      preview, adjustments form, final/timeline toggle, stats
  settings_dialog.py   fps, hotkeys, calibrate
  calibration_overlay.py  see calibration-overlay.md
  widgets.py           shared handle geometry, key capture
```

## Input panel

* Shows the source image scaled to fit. A crop rectangle with 4 corner and 4
  edge handles sits on top; drag inside to move, drag on empty area to draw a
  new rectangle. **Shift** keeps the aspect ratio, **Alt** resizes
  symmetrically around the center. **⟲** resets to the full image.
* The crop is stored **normalized (0..1)** so it survives loading a new image
  of a different size and persists across sessions.
* The output is 1:1, so the **centered square of the selection** is what gets
  drawn (crop to fit, never stretch). The editor shades the excluded strips and
  dashes the effective square.
* Transport: Play/Pause, Stop. Load file, Load clipboard.
* Timeline slider over every draw step. Scrubbing pauses; Play resumes from
  the slider position (the color is re-picked). Editing crop/adjustments is
  blocked while running and rebuilds the plan when paused/stopped.
* ⚙ opens Settings.

## Output panel

* Nearest-neighbour preview of the processed 32×32 image.
* Adjustments: palette limit, dither (two-pass quantize — Pillow ignores
  `dither` without an explicit palette), invert, brightness, contrast,
  saturation, gamma, alpha threshold. Every change re-runs the pipeline live.
* **Draw order** (`core/order.py`): per-color sequencing — horizontal, vertical,
  diagonal, spiral, trace (outline → fill per connected shape, biggest first),
  maze (seeded randomized DFS with a straight bias), scatter. Persisted with
  its seed in `ui_state.json`; 🎲 rerolls.
* **Color order** (`core/order.py`, `order_colors`): hex / hex reversed /
  dark→light / light→dark / biggest→smallest area / rainbow / random (seeded).
* **Show final result**: on = final image; off = pixels appear one by one as
  the timeline advances (same filters applied).
* Stats: colors (= color picker operations), steps, estimated time.

## Panels in general

* Frameless, always on top, movable by the title bar, resizable from every
  edge/corner.
* **⋮** menu: opacity slider, reset position, always-on-top toggle, hide panel, quit.
* **✕** quits the app (hiding is in ⋮ / the hotkey, so the app is never left
  running invisibly by accident).
* Geometry and opacity are saved to `ui_state.json` and restored on launch.

## Hotkeys

Global, so they work while the game has focus, but built on `Ctrl+Shift` so
they never type into chat and don't collide with AltGr layouts. The main key
must be one Roblox ignores even with modifiers held — Space (jump), W/A/S/D,
I/O (camera zoom), Esc, Tab are out; Settings warns about them.

| Action | Default |
|---|---|
| Play / Pause | Ctrl+Shift+P |
| Stop | Ctrl+Shift+X |
| Load image file | Ctrl+Shift+L |
| Load from clipboard | Ctrl+Shift+V |
| Reset crop | Ctrl+Shift+R |
| Show / hide panels | Ctrl+Shift+H |

All rebindable in Settings. Tooltips show the live binding.

## Later

* Stroke-based "hand drawing" pencil. `Drawer` calls a single
  `actuator.draw_step(step)` so the stroke engine can replace it without
  touching the UI.
