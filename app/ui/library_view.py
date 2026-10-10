from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QScrollArea, QTabWidget, QVBoxLayout, QWidget

from app import db
from app.config import SHELF_STATUSES
from app.services import reading
from app.ui.common import breakable, button, clear_layout, confirm, guarded, label
from app.ui.widgets import CoverLabel


def progress_text(row):
    if row.chapter_number:
        return f"Остановились на главе {row.chapter_number} из {row.total_chapters}: {row.chapter_title}"
    if row.total_chapters:
        return f"Ещё не начата · глав: {row.total_chapters}"
    return "Глав пока нет"


class ShelfRowWidget(QFrame):
    def __init__(self, row, view):
        super().__init__()
        self.setObjectName("Panel")
        book = row.entry.book
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 14, 18, 14)
        layout.setSpacing(18)
        cover = CoverLabel(74, 111, 6)
        cover.set_cover(book.cover_path, book.title, book.author.name)
        layout.addWidget(cover, 0, Qt.AlignmentFlag.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(4)
        info.addWidget(label(breakable(book.title), "CardTitle", wrap=True))
        info.addWidget(label(breakable(book.author.name), "CardAuthor", wrap=True))
        info.addWidget(label(breakable(progress_text(row)), "Muted", wrap=True))
        info.addStretch()
        layout.addLayout(info, 1)
        actions = QVBoxLayout()
        actions.setSpacing(6)
        read_text = "Продолжить чтение" if row.chapter_number else "Читать"
        read = button(read_text, "primary", lambda: view.window_ref.open_reader(book.id))
        read.setEnabled(row.total_chapters > 0)
        actions.addWidget(read)
        status = QComboBox()
        for value in SHELF_STATUSES:
            status.addItem(value.capitalize(), value)
        status.setCurrentIndex(status.findData(row.entry.status))
        status.currentIndexChanged.connect(lambda _index: view.change_status(book.id, status.currentData()))
        actions.addWidget(status)
        links = QHBoxLayout()
        links.addWidget(button("О книге", "flat", lambda: view.window_ref.open_book(book.id)))
        links.addWidget(button("Убрать", "flat", lambda: view.remove(book.id, book.title)))
        actions.addLayout(links)
        layout.addLayout(actions)


class LibraryView(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window_ref = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 16)
        layout.setSpacing(16)
        layout.addWidget(label("Моя библиотека", "PageTitle"))

        self.continue_panel = QFrame()
        self.continue_panel.setObjectName("Panel")
        panel_layout = QHBoxLayout(self.continue_panel)
        panel_layout.setContentsMargins(18, 16, 22, 16)
        panel_layout.setSpacing(18)
        self.continue_cover = CoverLabel(64, 96, 6)
        panel_layout.addWidget(self.continue_cover)
        texts = QVBoxLayout()
        texts.addWidget(label("Продолжить чтение", "Muted"))
        self.continue_title = label("", "SectionTitle", wrap=True)
        self.continue_progress = label("", "Muted", wrap=True)
        texts.addWidget(self.continue_title)
        texts.addWidget(self.continue_progress)
        panel_layout.addLayout(texts, 1)
        self.continue_button = button("Продолжить чтение", "primary", self.continue_reading)
        panel_layout.addWidget(self.continue_button)
        layout.addWidget(self.continue_panel)
        self.continue_book_id = None

        self.tabs = QTabWidget()
        self.tab_layouts = {}
        for status in SHELF_STATUSES:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            content = QWidget()
            tab_layout = QVBoxLayout(content)
            tab_layout.setContentsMargins(0, 12, 8, 12)
            tab_layout.setSpacing(12)
            scroll.setWidget(content)
            self.tabs.addTab(scroll, status.capitalize())
            self.tab_layouts[status] = tab_layout
        layout.addWidget(self.tabs, 1)

    @guarded
    def refresh(self):
        user = self.window_ref.user
        with db.session_scope() as session:
            last = reading.last_read(session, user)
            counts = reading.counts(session, user)
            rows = {status: reading.shelf_rows(session, user, status) for status in SHELF_STATUSES}
        self.continue_panel.setVisible(last is not None)
        if last is not None:
            book = last.entry.book
            self.continue_book_id = book.id
            self.continue_cover.set_cover(book.cover_path, book.title, book.author.name)
            self.continue_title.setText(breakable(f"{book.title} — {book.author.name}"))
            self.continue_progress.setText(breakable(progress_text(last)))
        for index, status in enumerate(SHELF_STATUSES):
            self.tabs.setTabText(index, f"{status.capitalize()} · {counts.get(status, 0)}")
            tab_layout = self.tab_layouts[status]
            clear_layout(tab_layout)
            for row in rows[status]:
                tab_layout.addWidget(ShelfRowWidget(row, self))
            if not rows[status]:
                empty = label("Здесь пока пусто", "EmptyState")
                empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
                tab_layout.addSpacing(40)
                tab_layout.addWidget(empty)
                hint = label("Добавляйте книги кнопкой «В библиотеку» на странице книги", "Muted")
                hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
                tab_layout.addWidget(hint)
            tab_layout.addStretch()

    def continue_reading(self):
        if self.continue_book_id is not None:
            self.window_ref.open_reader(self.continue_book_id)

    @guarded
    def change_status(self, book_id, status):
        with db.session_scope() as session:
            reading.set_status(session, self.window_ref.user, book_id, status)
        self.refresh()

    @guarded
    def remove(self, book_id, title):
        if not confirm(f"Убрать «{title}» из библиотеки?", self):
            return
        with db.session_scope() as session:
            reading.remove(session, self.window_ref.user, book_id)
        self.refresh()
