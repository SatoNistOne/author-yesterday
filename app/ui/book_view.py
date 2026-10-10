from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QBoxLayout,
    QDialog,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app import db
from app.config import SHELF_STATUSES
from app.services import books, reading
from app.services.rules import can_edit_book
from app.ui.common import breakable, button, clear_layout, confirm, guarded, label, rating_text, shorten
from app.ui.editors import ChapterEditor
from app.ui.widgets import CoverLabel, StarRating


STACK_WIDTH = 760


def votes_word(count):
    if count % 10 == 1 and count % 100 != 11:
        return "оценка"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return "оценки"
    return "оценок"


class BookView(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window_ref = window
        self.book_id = None
        self.can_edit = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        self.scroll = scroll

        layout = QVBoxLayout(content)
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)
        layout.setContentsMargins(32, 20, 32, 32)
        layout.setSpacing(16)
        top = QHBoxLayout()
        top.addWidget(button("← Назад", "flat", self.window_ref.go_back))
        top.addStretch()
        layout.addLayout(top)

        body = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        body.setSpacing(34)
        self.body = body
        left = QVBoxLayout()
        left.setSpacing(10)
        self.cover = CoverLabel(250, 375, 14)
        left.addWidget(self.cover)
        self.read_button = button("Читать", "primary", self.read)
        left.addWidget(self.read_button)
        self.shelf_button = QToolButton()
        self.shelf_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.shelf_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.shelf_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.shelf_button.setSizePolicy(self.read_button.sizePolicy())
        self.shelf_menu = QMenu(self.shelf_button)
        self.shelf_button.setMenu(self.shelf_menu)
        left.addWidget(self.shelf_button)
        left.addStretch()
        body.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(10)
        self.title = label("", "BookTitle", wrap=True)
        self.author = label("", "SectionTitle", wrap=True)
        self.meta = label("", "Muted")
        self.chips = QHBoxLayout()
        self.chips.setSpacing(6)
        rating_row = QHBoxLayout()
        self.rating_label = label("", "CardRating")
        rating_row.addWidget(self.rating_label)
        rating_row.addSpacing(24)
        rating_row.addWidget(label("Ваша оценка:", "Muted"))
        self.stars = StarRating()
        self.stars.rated.connect(self.rate)
        rating_row.addWidget(self.stars)
        rating_row.addStretch()
        self.description = label("", "Description", wrap=True)
        self.description.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.editor_row = QHBoxLayout()
        self.editor_row.addWidget(button("Изменить книгу", None, self.edit_book))
        self.editor_row.addWidget(button("＋ Глава", None, self.add_chapter))
        self.editor_row.addWidget(button("Удалить", "danger", self.delete_book))
        self.editor_row.addStretch()
        self.editor_box = QWidget()
        self.editor_box.setLayout(self.editor_row)
        self.editor_row.setContentsMargins(0, 4, 0, 4)

        right.addWidget(self.title)
        right.addWidget(self.author)
        right.addWidget(self.meta)
        right.addLayout(self.chips)
        right.addLayout(rating_row)
        right.addWidget(self.editor_box)
        right.addSpacing(6)
        right.addWidget(self.description)
        right.addSpacing(10)

        chapters_header = QHBoxLayout()
        chapters_header.addWidget(label("Оглавление", "SectionTitle"))
        chapters_header.addStretch()
        self.chapter_tools = QWidget()
        tools = QHBoxLayout(self.chapter_tools)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.addWidget(button("↑", None, lambda: self.move_chapter(-1), "Переместить выше"))
        tools.addWidget(button("↓", None, lambda: self.move_chapter(1), "Переместить ниже"))
        tools.addWidget(button("Изменить", None, self.edit_chapter))
        tools.addWidget(button("Удалить", "danger", self.delete_chapter))
        tools.addStretch()
        right.addLayout(chapters_header)
        self.chapter_list = QListWidget()
        self.chapter_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chapter_list.itemDoubleClicked.connect(self.open_chapter_item)
        right.addWidget(self.chapter_list)
        self.no_chapters = label("Глав пока нет", "Muted")
        right.addWidget(self.no_chapters)
        right.addWidget(self.chapter_tools)
        right.addStretch()
        body.addLayout(right, 1)
        layout.addLayout(body)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        direction = QBoxLayout.Direction.TopToBottom if self.width() < STACK_WIDTH else QBoxLayout.Direction.LeftToRight
        if self.body.direction() != direction:
            self.body.setDirection(direction)

    def refresh(self):
        if self.book_id is not None:
            self.load(self.book_id)

    @guarded
    def load(self, book_id, register_view=False):
        self.book_id = book_id
        user = self.window_ref.user
        with db.session_scope() as session:
            book = books.register_view(session, book_id) if register_view else books.get_book(session, book_id)
            average, votes = books.average(session, book_id)
            own = books.user_rating(session, user, book_id)
            entry = reading.get_entry(session, user, book_id)
            shelf = entry.status if entry else None
            position, _scroll = reading.get_position(session, user, book_id)
            chapter_rows = [(chapter.id, chapter.number, chapter.title) for chapter in book.chapters]
            self.can_edit = can_edit_book(user, book)
            title, author_name, description = book.title, book.author.name, book.description
            status, views, cover_path = book.status, book.views, book.cover_path
            genre_names = [genre.name for genre in book.genres]

        self.cover.set_cover(cover_path, title, author_name)
        self.title.setText(breakable(shorten(title, 90), 16))
        self.title.setToolTip(breakable(title, 60) if len(title) > 90 else "")
        self.author.setText(breakable(author_name))
        self.meta.setText(f"{status.capitalize()} · глав: {len(chapter_rows)} · просмотров: {views}")
        clear_layout(self.chips)
        for name in genre_names:
            self.chips.addWidget(label(name, "Chip"))
        self.chips.addStretch()
        self.rating_label.setText(
            rating_text(average, votes) if not votes else f"★ {average:.1f}".replace(".", ",") + f"  · {votes} {votes_word(votes)}"
        )
        self.stars.set_value(own or 0)
        self.description.setText(breakable(description, 40))
        self.editor_box.setVisible(self.can_edit)
        self.chapter_tools.setVisible(self.can_edit and bool(chapter_rows))

        self.chapter_list.clear()
        for chapter_id, number, chapter_title in chapter_rows:
            item = QListWidgetItem(f"{number}.  {chapter_title[:160]}")
            item.setToolTip(breakable(chapter_title, 60))
            item.setData(Qt.ItemDataRole.UserRole, chapter_id)
            self.chapter_list.addItem(item)
        row_height = self.chapter_list.sizeHintForRow(0) if chapter_rows else 0
        self.chapter_list.setFixedHeight(row_height * len(chapter_rows) + 14)
        self.chapter_list.setVisible(bool(chapter_rows))
        self.no_chapters.setVisible(not chapter_rows)

        self.read_button.setEnabled(bool(chapter_rows))
        self.read_button.setText("Продолжить чтение" if position else "Читать")
        self._build_shelf_menu(shelf)
        if register_view:
            self.scroll.verticalScrollBar().setValue(0)

    def _build_shelf_menu(self, shelf):
        self.shelf_menu.clear()
        self.shelf_button.setText(f"В библиотеке: {shelf}" if shelf else "В библиотеку")
        for status in SHELF_STATUSES:
            action = self.shelf_menu.addAction(status.capitalize())
            action.setCheckable(True)
            action.setChecked(status == shelf)
            action.triggered.connect(lambda _checked=False, value=status: self.set_shelf(value))
        if shelf:
            self.shelf_menu.addSeparator()
            self.shelf_menu.addAction("Убрать из библиотеки").triggered.connect(self.remove_from_shelf)

    @guarded
    def set_shelf(self, status):
        with db.session_scope() as session:
            reading.set_status(session, self.window_ref.user, self.book_id, status)
        self.load(self.book_id)

    @guarded
    def remove_from_shelf(self):
        with db.session_scope() as session:
            reading.remove(session, self.window_ref.user, self.book_id)
        self.load(self.book_id)

    @guarded
    def rate(self, value):
        with db.session_scope() as session:
            books.rate(session, self.window_ref.user, self.book_id, value)
        self.load(self.book_id)

    def read(self):
        self.window_ref.open_reader(self.book_id)

    def open_chapter_item(self, item):
        self.window_ref.open_reader(self.book_id, item.data(Qt.ItemDataRole.UserRole))

    def selected_chapter(self):
        item = self.chapter_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def edit_book(self):
        self.window_ref.edit_book(self.book_id)

    @guarded
    def delete_book(self):
        if not confirm(f"Удалить книгу «{self.title.text()}» вместе со всеми главами?", self):
            return
        with db.session_scope() as session:
            books.delete_book(session, self.window_ref.user, self.book_id)
        self.book_id = None
        self.window_ref.go_back()

    def add_chapter(self):
        dialog = ChapterEditor(self.window_ref.user, self.book_id, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load(self.book_id)

    def _require_selection(self):
        chapter_id = self.selected_chapter()
        if chapter_id is None:
            self.window_ref.notify("Выберите главу в оглавлении")
        return chapter_id

    def edit_chapter(self):
        chapter_id = self._require_selection()
        if chapter_id is None:
            return
        dialog = ChapterEditor(self.window_ref.user, self.book_id, chapter_id, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.load(self.book_id)

    @guarded
    def delete_chapter(self):
        chapter_id = self._require_selection()
        if chapter_id is None or not confirm("Удалить выбранную главу?", self):
            return
        with db.session_scope() as session:
            reading.delete_chapter(session, self.window_ref.user, chapter_id)
        self.load(self.book_id)

    @guarded
    def move_chapter(self, offset):
        chapter_id = self._require_selection()
        if chapter_id is None:
            return
        with db.session_scope() as session:
            reading.move_chapter(session, self.window_ref.user, chapter_id, offset)
        self.load(self.book_id)
        for row in range(self.chapter_list.count()):
            if self.chapter_list.item(row).data(Qt.ItemDataRole.UserRole) == chapter_id:
                self.chapter_list.setCurrentRow(row)
