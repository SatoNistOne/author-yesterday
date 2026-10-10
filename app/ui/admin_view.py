from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app import db
from app.config import ROLE_TITLES, ROLES
from app.services import auth, books
from app.services.rules import GENRE_MAX, USERNAME_MAX
from app.ui.common import button, confirm, guarded, label


def cell(text, align_center=False):
    item = QTableWidgetItem(str(text))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    if align_center:
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    return item


def padded(widget):
    holder = QWidget()
    layout = QHBoxLayout(holder)
    layout.setContentsMargins(6, 4, 6, 4)
    layout.addWidget(widget)
    return holder


def fix_widths(widget, widths):
    header = widget.horizontalHeader()
    for column, width in widths.items():
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.Fixed)
        widget.setColumnWidth(column, width)


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.verticalHeader().setVisible(False)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.setAlternatingRowColors(True)
    widget.setShowGrid(False)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    widget.verticalHeader().setDefaultSectionSize(50)
    return widget


class AdminView(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window_ref = window
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(14)
        layout.addWidget(label("Администрирование", "PageTitle"))
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_users(), "Пользователи")
        self.tabs.addTab(self._build_books(), "Книги")
        self.tabs.addTab(self._build_genres(), "Жанры")
        layout.addWidget(self.tabs, 1)

    def _build_users(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        self.user_filter = QLineEdit()
        self.user_filter.setPlaceholderText("Фильтр по логину или имени…")
        self.user_filter.setMaxLength(USERNAME_MAX)
        self.user_filter.textChanged.connect(self.load_users)
        layout.addWidget(self.user_filter)
        self.users_table = table(["Логин", "Имя", "Роль", "Статус", "Зарегистрирован", ""])
        self.users_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        fix_widths(self.users_table, {2: 190, 3: 130, 4: 150, 5: 180})
        layout.addWidget(self.users_table, 1)
        return page

    def _build_books(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        self.books_table = table(["Название", "Автор", "Глав", "Просмотры", "Рейтинг", ""])
        self.books_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        fix_widths(self.books_table, {5: 140})
        self.books_table.cellDoubleClicked.connect(self._open_book_row)
        layout.addWidget(self.books_table, 1)
        layout.addWidget(label("Двойной щелчок по строке открывает страницу книги", "Muted"))
        return page

    def _build_genres(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 14, 0, 0)
        layout.setSpacing(18)
        self.genre_list = QListWidget()
        self.genre_list.setMaximumWidth(420)
        self.genre_list.itemDoubleClicked.connect(lambda _item: self.rename_genre())
        layout.addWidget(self.genre_list, 1)
        side = QVBoxLayout()
        self.genre_name = QLineEdit()
        self.genre_name.setPlaceholderText("Название нового жанра")
        self.genre_name.setMaxLength(GENRE_MAX)
        self.genre_name.returnPressed.connect(self.add_genre)
        side.addWidget(self.genre_name)
        side.addWidget(button("Добавить жанр", "primary", self.add_genre))
        side.addSpacing(12)
        side.addWidget(button("Переименовать выбранный", None, self.rename_genre))
        side.addWidget(button("Удалить выбранный", "danger", self.delete_genre))
        side.addSpacing(12)
        side.addWidget(label("Удаление жанра не удаляет книги — они просто теряют эту метку.", "Muted", wrap=True))
        side.addStretch()
        layout.addLayout(side, 1)
        return page

    def refresh(self):
        self.load_users()
        self.load_books()
        self.load_genres()

    @guarded
    def load_users(self, *_args):
        query = self.user_filter.text().casefold().strip()
        with db.session_scope() as session:
            rows = [
                (user.id, user.username, user.name, user.role, user.is_blocked, user.created_at)
                for user in auth.list_users(session)
                if not query or query in user.username.casefold() or query in user.name.casefold()
            ]
        me = self.window_ref.user.id
        self.users_table.setRowCount(len(rows))
        for row, (user_id, username, name, role, blocked, created) in enumerate(rows):
            self.users_table.setItem(row, 0, cell(username))
            self.users_table.setItem(row, 1, cell(name))
            role_combo = QComboBox()
            for value in ROLES:
                role_combo.addItem(ROLE_TITLES[value], value)
            role_combo.setCurrentIndex(role_combo.findData(role))
            role_combo.setEnabled(user_id != me)
            role_combo.currentIndexChanged.connect(
                lambda _index, uid=user_id, combo=role_combo: self.change_role(uid, combo.currentData())
            )
            self.users_table.setCellWidget(row, 2, padded(role_combo))
            self.users_table.setItem(row, 3, cell("Заблокирован" if blocked else "Активен"))
            self.users_table.setItem(row, 4, cell(created.strftime("%d.%m.%Y")))
            action = button("Разблокировать" if blocked else "Заблокировать", None if blocked else "danger",
                            lambda uid=user_id, value=not blocked, login=username: self.set_blocked(uid, value, login))
            action.setEnabled(user_id != me)
            self.users_table.setCellWidget(row, 5, padded(action))

    @guarded
    def set_blocked(self, user_id, blocked, username):
        if blocked and not confirm(f"Заблокировать пользователя «{username}»? Он не сможет войти в приложение.", self):
            return
        with db.session_scope() as session:
            auth.set_blocked(session, self.window_ref.user, user_id, blocked)
        self.load_users()

    @guarded
    def change_role(self, user_id, role):
        with db.session_scope() as session:
            auth.set_role(session, self.window_ref.user, user_id, role)
        self.load_users()

    @guarded
    def load_books(self):
        with db.session_scope() as session:
            items = books.search_books(session, sort="title")
            rows = [
                (item.book.id, item.book.title, item.book.author.name, len(item.book.chapters), item.book.views, item.rating, item.votes)
                for item in items
            ]
        self.books_table.setRowCount(len(rows))
        for row, (book_id, title, author, chapter_count, views, rating, votes) in enumerate(rows):
            title_item = cell(title)
            title_item.setData(Qt.ItemDataRole.UserRole, book_id)
            self.books_table.setItem(row, 0, title_item)
            self.books_table.setItem(row, 1, cell(author))
            self.books_table.setItem(row, 2, cell(chapter_count, True))
            self.books_table.setItem(row, 3, cell(views, True))
            self.books_table.setItem(row, 4, cell(f"{rating:.1f} ({votes})".replace(".", ",") if votes else "—", True))
            remove = button("Удалить", "danger", lambda bid=book_id, name=title: self.delete_book(bid, name))
            self.books_table.setCellWidget(row, 5, padded(remove))

    def _open_book_row(self, row, _column):
        item = self.books_table.item(row, 0)
        if item is not None:
            self.window_ref.open_book(item.data(Qt.ItemDataRole.UserRole))

    @guarded
    def delete_book(self, book_id, title):
        if not confirm(f"Удалить книгу «{title}» вместе со всеми главами, оценками и закладками?", self):
            return
        with db.session_scope() as session:
            books.delete_book(session, self.window_ref.user, book_id)
        self.load_books()

    @guarded
    def load_genres(self):
        with db.session_scope() as session:
            rows = [(genre.id, genre.name, count) for genre, count in books.genres_with_books(session)]
        self.genre_list.clear()
        for genre_id, name, count in rows:
            item = QListWidgetItem(f"{name}  ·  {count}")
            item.setData(Qt.ItemDataRole.UserRole, (genre_id, name))
            self.genre_list.addItem(item)

    def _selected_genre(self):
        item = self.genre_list.currentItem()
        if item is None:
            self.window_ref.notify("Выберите жанр в списке")
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    @guarded
    def add_genre(self):
        with db.session_scope() as session:
            books.create_genre(session, self.window_ref.user, self.genre_name.text())
        self.genre_name.clear()
        self.load_genres()

    @guarded
    def rename_genre(self):
        selected = self._selected_genre()
        if selected is None:
            return
        genre_id, name = selected
        new_name, accepted = QInputDialog.getText(self, "Переименование жанра", "Новое название:", text=name)
        if not accepted:
            return
        with db.session_scope() as session:
            books.rename_genre(session, self.window_ref.user, genre_id, new_name)
        self.load_genres()

    @guarded
    def delete_genre(self):
        selected = self._selected_genre()
        if selected is None:
            return
        genre_id, name = selected
        if not confirm(f"Удалить жанр «{name}»?", self):
            return
        with db.session_scope() as session:
            books.delete_genre(session, self.window_ref.user, genre_id)
        self.load_genres()
