import logging
import sys

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QFrame, QProgressBar, QVBoxLayout

from app import db
from app.config import APP_NAME, assets_dir, setup_logging
from app.seed import needs_seed, seed_if_empty
from app.ui import theme
from app.ui.common import label, show_error
from app.ui.login_dialog import LoginDialog
from app.ui.main_window import MainWindow

log = logging.getLogger("author_yesterday")


class SeedWorker(QThread):
    progressed = Signal(int, int, str)
    failed = Signal(str)

    def run(self):
        try:
            seed_if_empty(lambda done, total, text: self.progressed.emit(done, total, text))
        except Exception as error:
            log.exception("Ошибка подготовки демо-данных")
            self.failed.emit(str(error))


class SeedDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.error = None
        self.setWindowTitle("Author Yesterday")
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setModal(True)
        self.setFixedWidth(460)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 18, 18, 18)
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(12)
        title = label("Author Yesterday", "AuthTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(label("Первый запуск: готовим библиотеку", "SectionTitle"))
        self.status = label("Подготовка…", "Muted", wrap=True)
        layout.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)
        self.bar.setTextVisible(False)
        layout.addWidget(self.bar)
        outer.addWidget(panel)
        self.worker = SeedWorker(self)
        self.worker.progressed.connect(self._on_progress)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_finished)

    def exec(self):
        self.worker.start()
        return super().exec()

    def _on_progress(self, done, total, text):
        self.bar.setRange(0, total)
        self.bar.setValue(done)
        self.status.setText(f"{done} из {total - 1}: {text}" if done else text)

    def _on_failed(self, message):
        self.error = message

    def _on_finished(self):
        if self.error:
            self.reject()
        else:
            self.accept()

    def reject(self):
        if self.worker.isRunning():
            return
        super().reject()


def install_exception_hook():
    def hook(exc_type, exc_value, exc_traceback):
        log.error("Необработанная ошибка", exc_info=(exc_type, exc_value, exc_traceback))
        show_error(f"Непредвиденная ошибка: {exc_value}")

    sys.excepthook = hook


def ask_login(window=None):
    dialog = LoginDialog(window)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.user


def prepare_database():
    db.init_db()
    if not needs_seed():
        seed_if_empty()
        return True
    dialog = SeedDialog()
    dialog.exec()
    if dialog.error:
        show_error(f"Не удалось подготовить демо-данные: {dialog.error}")
        return False
    return True


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(str(assets_dir() / "icon.ico")))
    setup_logging()
    install_exception_hook()
    theme.load_fonts()
    theme.apply_theme(app, theme.saved_theme())
    try:
        if not prepare_database():
            return 1
    except Exception as error:
        log.exception("Не удалось открыть базу данных")
        show_error(f"Не удалось открыть базу данных: {error}")
        return 1
    user = ask_login()
    if user is None:
        return 0
    window = MainWindow(app)

    def relogin():
        window.hide()
        next_user = ask_login()
        if next_user is None:
            app.quit()
            return
        window.set_user(next_user)
        window.show()

    window.logout_requested.connect(relogin)
    window.set_user(user)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
