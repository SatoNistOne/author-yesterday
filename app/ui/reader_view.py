import html
import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QTextBrowser, QVBoxLayout, QWidget

from app import db
from app.services import books, reading
from app.ui import theme
from app.ui.common import breakable, button, guarded, label


MIN_FONT = 11
MAX_FONT = 28
DEFAULT_FONT = 15
TEXT_WIDTH = 760
COMPACT_WIDTH = 860
SCROLL_SCALE = 10000


def chapter_html(title, content):
    paragraphs = [part.strip() for part in content.replace("\r\n", "\n").split("\n\n") if part.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [line.strip() for line in content.splitlines() if line.strip()]
    body = "".join(f"<p>{html.escape(paragraph).replace(chr(10), '<br>')}</p>" for paragraph in paragraphs)
    return f"<h2>{html.escape(title)}</h2>{body}"


class ReaderText(QTextBrowser):
    def __init__(self):
        super().__init__()
        self.setObjectName("ReaderText")
        self.setOpenLinks(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def resizeEvent(self, event):
        side = max(18, (self.width() - TEXT_WIDTH) // 2)
        self.setViewportMargins(side, 0, side, 0)
        super().resizeEvent(event)


class ReaderView(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window_ref = window
        self.book_id = None
        self.chapter_id = None
        self.previous_id = None
        self.next_id = None
        self.font_size = int(theme.settings().value("reader_font", DEFAULT_FONT))
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(700)
        self.save_timer.timeout.connect(self.save_position)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        bar = QFrame()
        bar.setObjectName("ReaderBar")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(18, 10, 18, 10)
        bar_layout.setSpacing(8)
        bar_layout.addWidget(button("← К книге", "flat", self.back_to_book))
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.book_label = label("", "Muted")
        self.chapter_label = label("", "CardTitle")
        titles.addWidget(self.book_label)
        titles.addWidget(self.chapter_label)
        bar_layout.addSpacing(10)
        bar_layout.addLayout(titles, 1)
        bar_layout.addWidget(button("A−", None, lambda: self.change_font(-1), "Уменьшить шрифт"))
        self.size_label = label("", "Muted")
        self.size_label.setMinimumWidth(28)
        self.size_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar_layout.addWidget(self.size_label)
        bar_layout.addWidget(button("A+", None, lambda: self.change_font(1), "Увеличить шрифт"))
        self.theme_button = button("", None, self.toggle_theme, "Светлая или тёмная тема")
        bar_layout.addWidget(self.theme_button)
        bar_layout.addSpacing(10)
        self.prev_button = button("← Предыдущая", None, lambda: self.open_chapter(self.previous_id))
        self.next_button = button("Следующая →", "primary", lambda: self.open_chapter(self.next_id))
        bar_layout.addWidget(self.prev_button)
        bar_layout.addWidget(self.next_button)
        layout.addWidget(bar)

        self.text = ReaderText()
        self.text.verticalScrollBar().valueChanged.connect(lambda _value: self.save_timer.start())
        layout.addWidget(self.text, 1)
        self._apply_font()
        self._update_theme_button()

    def refresh(self):
        self._update_theme_button()

    def on_theme_changed(self):
        self._update_theme_button()
        self._apply_font()

    def _update_theme_button(self):
        self.theme_button.setText("☾" if theme.current_name() == "light" else "☀")

    def toggle_theme(self):
        self.window_ref.toggle_theme()

    def _apply_font(self):
        ratio = self._scroll_ratio()
        self.text.setFont(theme.serif_font(self.font_size))
        self.text.setStyleSheet(f'font-family: "{theme.SERIF}"; font-size: {self.font_size}pt;')
        self.text.document().setDefaultStyleSheet(
            f"p {{ margin-top: 0; margin-bottom: {self.font_size * 0.9:.0f}px; line-height: 140%; text-indent: 1.5em; }}"
            f"h2 {{ font-size: {self.font_size + 9}pt; margin-top: 36px; margin-bottom: 28px; }}"
        )
        if self.chapter_id is not None:
            self.text.setHtml(self.current_html)
            self._restore_scroll(ratio)
        self.size_label.setText(str(self.font_size))

    def change_font(self, delta):
        self.font_size = max(MIN_FONT, min(MAX_FONT, self.font_size + delta))
        theme.settings().setValue("reader_font", self.font_size)
        self._apply_font()

    def _scroll_ratio(self):
        bar = self.text.verticalScrollBar()
        return bar.value() / bar.maximum() if bar.maximum() > 0 else 0

    def _restore_scroll(self, ratio):
        def apply():
            bar = self.text.verticalScrollBar()
            bar.setValue(round(ratio * bar.maximum()))

        QTimer.singleShot(0, apply)
        QTimer.singleShot(60, apply)

    @guarded
    def open_book(self, book_id, chapter_id=None):
        self.save_position()
        user = self.window_ref.user
        ratio = 0
        with db.session_scope() as session:
            book = books.get_book(session, book_id)
            saved_chapter, saved_scroll = reading.get_position(session, user, book_id)
            if chapter_id is None:
                chapter_id = saved_chapter or (book.chapters[0].id if book.chapters else None)
            if chapter_id is not None and chapter_id == saved_chapter:
                ratio = saved_scroll / SCROLL_SCALE
            self.book_title = book.title
            self.author_name = book.author.name
        if chapter_id is None:
            self.window_ref.notify("В книге пока нет глав")
            return False
        self.book_id = book_id
        self._load_chapter(chapter_id, ratio)
        return True

    @guarded
    def open_chapter(self, chapter_id):
        if chapter_id is None:
            return
        self.save_position()
        self._load_chapter(chapter_id, 0)

    def _load_chapter(self, chapter_id, ratio):
        with db.session_scope() as session:
            chapter = reading.get_chapter(session, chapter_id)
            previous, following = reading.neighbours(session, chapter)
            total = len(reading.list_chapters(session, chapter.book_id))
            number, title, content = chapter.number, chapter.title, chapter.content
            self.previous_id = previous.id if previous else None
            self.next_id = following.id if following else None
        self.chapter_id = chapter_id
        self.current_html = chapter_html(title, content)
        self.book_label.setText(self._elide(self.book_label, f"{self.book_title} · {self.author_name}"))
        self.chapter_label.setText(self._elide(self.chapter_label, f"Глава {number} из {total}: {title}"))
        self.prev_button.setEnabled(self.previous_id is not None)
        self.next_button.setEnabled(self.next_id is not None)
        self.text.verticalScrollBar().blockSignals(True)
        self.text.setHtml(self.current_html)
        self.text.verticalScrollBar().blockSignals(False)
        self._restore_scroll(ratio)
        self.save_timer.start()

    def _elide(self, widget, text):
        widget.setToolTip(breakable(text, 60))
        return widget.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, 420)

    def save_position(self):
        self.save_timer.stop()
        if self.book_id is None or self.chapter_id is None or self.window_ref.user is None:
            return
        try:
            with db.session_scope() as session:
                reading.save_position(
                    session, self.window_ref.user, self.book_id, self.chapter_id, round(self._scroll_ratio() * SCROLL_SCALE)
                )
        except Exception:
            logging.getLogger(__name__).exception("Не удалось сохранить позицию чтения")

    def back_to_book(self):
        self.save_position()
        self.window_ref.open_book(self.book_id, register_view=False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        compact = self.width() < COMPACT_WIDTH
        self.book_label.setVisible(not compact)
        self.prev_button.setText("←" if compact else "← Предыдущая")
        self.next_button.setText("→" if compact else "Следующая →")
        self.prev_button.setToolTip("Предыдущая глава")
        self.next_button.setToolTip("Следующая глава")

    def hideEvent(self, event):
        self.save_position()
        super().hideEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Right and self.next_id:
            self.open_chapter(self.next_id)
        elif event.key() == Qt.Key.Key_Left and self.previous_id:
            self.open_chapter(self.previous_id)
        else:
            super().keyPressEvent(event)
