import sys

from pathlib import Path

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from .config.settings import ConfigError, Settings, load_settings
from .ui.main_window import MainWindow
from .ui.theme import AppleStyleSheet, fade_in


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("bgtrainer")
    app.setDesktopFileName("bgtrainer")  # associe la fenêtre à l'icône sous Linux (Wayland)
    icon = QIcon(str(Path(__file__).with_name("ui") / "assets" / "icon.png"))
    app.setWindowIcon(icon)
    style = AppleStyleSheet(app)
    style.apply_system_theme()  # clair/sombre automatique, suit macOS
    try:
        settings = load_settings()
    except ConfigError as e:
        QMessageBox.warning(None, "Configuration invalide", f"{e}\nValeurs par défaut utilisées.")
        settings = Settings()
    w = MainWindow(settings)
    w.resize(1250, 780)
    w.showMaximized()
    fade_in(w)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
