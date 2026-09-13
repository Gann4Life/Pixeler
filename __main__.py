'''Pixeler entry point: two floating panels (Input / Output) that stay on top of
the game, global hotkeys, and the calibration overlay. See docs/ui-rework.md.'''
import os
import sys

# Qt must report physical pixels so its coordinates match what autoit clicks.
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
os.environ.setdefault("QT_SCALE_FACTOR", "1")

# Run from the repo folder regardless of the caller's cwd (config.json, resources/, ui_state.json).
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.getcwd())

from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.app import PixelerApp  # noqa: E402
from ui.input_panel import InputPanel  # noqa: E402
from ui.output_panel import OutputPanel  # noqa: E402
from ui.status_panel import StatusPanel  # noqa: E402
from ui.settings_dialog import SettingsDialog  # noqa: E402
from ui.calibration_overlay import CalibrationOverlay  # noqa: E402


def main():
    qapp = QApplication(sys.argv)
    qapp.setApplicationName("Pixeler")
    qapp.setQuitOnLastWindowClosed(False)   # hiding both panels must not quit; ⋮ → Quit does

    app = PixelerApp()
    input_panel = InputPanel(app)
    output_panel = OutputPanel(app)
    status_panel = StatusPanel(app)
    app.panels = [input_panel, output_panel, status_panel]

    overlay = {"w": None}

    def open_calibration():
        if overlay["w"] is not None:
            return
        app.hotkeys.enabled = False
        for p in app.panels:
            p.hide()
        w = CalibrationOverlay(app.calibration, app.pencil)
        overlay["w"] = w

        def done():
            overlay["w"] = None
            app.hotkeys.enabled = True
            for p in app.panels:
                p.show()
            app.rebuild()   # stats/ETA depend on fps
        w.closed.connect(done)
        w.show()
        w.activateWindow()
        w.setFocus()

    def open_settings():
        dlg = SettingsDialog(app, input_panel)
        dlg.calibrate_requested.connect(lambda: (dlg.reject(), open_calibration()))
        dlg.exec()
        input_panel.refresh_tooltips()
        status_panel.refresh_hint()
        app.rebuild()

    input_panel.open_settings = open_settings

    def quit_app():
        app.shutdown()
        qapp.quit()
    for p in app.panels:
        p.quit_requested.connect(quit_app)
    qapp.aboutToQuit.connect(app.shutdown)

    # Each panel's ⋮ menu can bring the other one back if it was hidden.
    for p in app.panels:
        for other in app.panels:
            if other is not p:
                p.add_menu_action(f"Show {other.title_label.text()} panel", other.show)

    # Always start with both panels visible; only geometry/opacity persist.
    for p in app.panels:
        p.show()

    app.start()
    app.rebuild()
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):   # `python . image.png`
        app.load_file(sys.argv[1])
    if not app.calibration.is_config_valid():
        app.status.emit("Not calibrated yet — open ⚙ to calibrate.", True)
    sys.exit(qapp.exec())


if __name__ == "__main__":
    main()
