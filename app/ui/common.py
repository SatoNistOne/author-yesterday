import functools
import inspect
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QMessageBox, QPushButton

from app.services.rules import ServiceError


def active_window():
    return QApplication.activeWindow()


def show_warning(message, parent=None):
    QMessageBox.warning(parent or active_window(), "Author Yesterday", str(message))


def show_error(message, parent=None):
    QMessageBox.critical(parent or active_window(), "Author Yesterday", str(message))


def show_info(message, parent=None):
    QMessageBox.information(parent or active_window(), "Author Yesterday", str(message))


def confirm(message, parent=None):
    answer = QMessageBox.question(
        parent or active_window(),
        "Подтверждение",
        message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


def guarded(method):
    parameters = inspect.signature(method).parameters.values()
    variadic = any(parameter.kind == parameter.VAR_POSITIONAL for parameter in parameters)
    positional = sum(parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD) for parameter in parameters)

    @functools.wraps(method)
    def wrapper(*args, **kwargs):
        if not variadic:
            args = args[:positional]
        try:
            return method(*args, **kwargs)
        except ServiceError as error:
            show_warning(error)
        except Exception as error:
            logging.getLogger(__name__).exception("Непредвиденная ошибка")
            show_error(f"Непредвиденная ошибка: {error}")
        return None

    return wrapper


def button(text, kind=None, on_click=None, tooltip=None):
    widget = QPushButton(text)
    if kind:
        widget.setProperty("kind", kind)
    if on_click is not None:
        widget.clicked.connect(lambda _checked=False: on_click())
    if tooltip:
        widget.setToolTip(tooltip)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    return widget


def label(text="", name=None, wrap=False):
    widget = QLabel(text)
    if name:
        widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def separator():
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setObjectName("Muted")
    return line


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def breakable(text, chunk=18):
    words = []
    for word in str(text).split(" "):
        if len(word) > chunk:
            word = "\u200b".join(word[index:index + chunk] for index in range(0, len(word), chunk))
        words.append(word)
    return " ".join(words)


def shorten(text, limit):
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def rating_text(value, votes):
    if not votes:
        return "☆ нет оценок"
    return f"★ {value:.1f}".replace(".", ",") + f"  ({votes})"


def available_geometry(widget=None):
    screen = widget.screen() if widget is not None and widget.screen() else QGuiApplication.primaryScreen()
    return screen.availableGeometry()


def fit_to_screen(widget, width, height, ratio=0.92):
    area = available_geometry(widget)
    target_width = min(width, int(area.width() * ratio))
    target_height = min(height, int(area.height() * ratio))
    widget.resize(target_width, target_height)
    widget.move(area.x() + (area.width() - target_width) // 2, area.y() + (area.height() - target_height) // 2)
