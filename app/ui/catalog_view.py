from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QMenu, QScrollArea, QToolButton, QVBoxLayout, QWidget

from app import db
from app.config import BOOK_STATUSES, SEARCH_DEBOUNCE_MS, SORT_NEW, SORT_TITLES
from app.services import books
from app.services.rules import can_write, is_admin, SEARCH_MAX
from app.ui.common import button, guarded, label
from app.ui.widgets import BookCard, CardGrid


PAGE_SIZE = 40
MIN_RATINGS = (("Любой рейтинг", 0), ("от 3 ★", 3), ("от 4 ★", 4), ("от 4,5 ★", 4.5))


class CatalogView(QWidget):
    def __init__(self, window, mine=False):
        super().__init__()
        self.window_ref = window
        self.mine = mine
        self.genre_actions = {}
        self.items = []
        self.shown = 0
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(SEARCH_DEBOUNCE_MS)
        self.debounce.timeout.connect(self.reload)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 26, 0)
        layout.setSpacing(14)

        header = QHBoxLayout()
        self.title = label("Мои книги" if mine else "Каталог", "PageTitle")
        header.addWidget(self.title)
        header.addStretch()
        self.count_label = label("", "Muted")
        header.addWidget(self.count_label)
        if mine:
            header.addSpacing(12)
            header.addWidget(button("＋  Новая книга", "primary", self.create_book))
        layout.addLayout(header)

        filters = QHBoxLayout()
        filters.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по названию, автору или описанию…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(260)
        self.search.setMaxLength(SEARCH_MAX)
        self.search.textChanged.connect(lambda _text: self.debounce.start())
        filters.addWidget(self.search, 1)
        filters.addWidget(self._build_sort_combo())
        layout.addLayout(filters)
        filters = QHBoxLayout()
        filters.setSpacing(10)

        self.genre_button = QToolButton()
        self.genre_button.setText("Жанры")
        self.genre_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.genre_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.genre_menu = QMenu(self.genre_button)
        self.genre_button.setMenu(self.genre_menu)
        filters.addWidget(self.genre_button)

        self.status_combo = QComboBox()
        self.status_combo.addItem("Любой статус", None)
        for status in BOOK_STATUSES:
            self.status_combo.addItem(status.capitalize(), status)
        self.status_combo.currentIndexChanged.connect(self.reload)
        filters.addWidget(self.status_combo)

        self.rating_combo = QComboBox()
        for text, value in MIN_RATINGS:
            self.rating_combo.addItem(text, value)
        self.rating_combo.currentIndexChanged.connect(self.reload)
        filters.addWidget(self.rating_combo)

        self.reset_button = button("Сбросить фильтры", "flat", self.reset_filters)
        filters.addWidget(self.reset_button)
        filters.addStretch()
        layout.addLayout(filters)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 4, 0, 0)
        self.grid = CardGrid()
        container_layout.addWidget(self.grid)
        self.more_button = button("Показать ещё", None, self.show_more)
        more_row = QHBoxLayout()
        more_row.addStretch()
        more_row.addWidget(self.more_button)
        more_row.addStretch()
        container_layout.addLayout(more_row)
        self.empty = label("Ничего не найдено", "EmptyState")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint = label("Попробуйте изменить запрос или сбросить фильтры", "Muted")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addSpacing(10)
        container_layout.addWidget(self.empty)
        container_layout.addWidget(self.empty_hint)
        container_layout.addStretch()
        self.scroll.setWidget(container)
        layout.addWidget(self.scroll, 1)

    def _build_sort_combo(self):
        self.sort_combo = QComboBox()
        for key, text in SORT_TITLES.items():
            self.sort_combo.addItem(text, key)
        self.sort_combo.setCurrentIndex(self.sort_combo.findData(SORT_NEW))
        self.sort_combo.currentIndexChanged.connect(self.reload)
        return self.sort_combo

    def refresh(self):
        self._load_genres()
        self.reload()

    def on_theme_changed(self):
        for card in self.grid.cards:
            card.update_shadow_color()

    def _load_genres(self):
        checked = set(self.selected_genres())
        self.genre_menu.clear()
        self.genre_actions = {}
        with db.session_scope() as session:
            items = [(genre.id, genre.name) for genre in books.list_genres(session)]
        for genre_id, name in items:
            action = self.genre_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(genre_id in checked)
            action.toggled.connect(lambda _checked: self._genres_changed())
            self.genre_actions[genre_id] = action
        self._update_genre_button()

    def selected_genres(self):
        return [genre_id for genre_id, action in self.genre_actions.items() if action.isChecked()]

    def _genres_changed(self):
        self._update_genre_button()
        self.reload()

    def _update_genre_button(self):
        count = len(self.selected_genres())
        self.genre_button.setText(f"Жанры · {count}" if count else "Жанры")

    def reset_filters(self):
        for action in self.genre_actions.values():
            action.blockSignals(True)
            action.setChecked(False)
            action.blockSignals(False)
        for combo in (self.status_combo, self.rating_combo):
            combo.blockSignals(True)
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._update_genre_button()
        self.reload()

    def _author_filter(self):
        user = self.window_ref.user
        if not self.mine or user is None or is_admin(user):
            return None
        return user.id

    @guarded
    def reload(self):
        self.debounce.stop()
        with db.session_scope() as session:
            items = books.search_books(
                session,
                query=self.search.text(),
                genre_ids=self.selected_genres(),
                status=self.status_combo.currentData(),
                min_rating=self.rating_combo.currentData() or 0,
                sort=self.sort_combo.currentData(),
                author_id=self._author_filter(),
            )
        self.items = items
        self.shown = 0
        self.grid.set_cards([])
        self.show_more()
        has_results = bool(items)
        self.grid.setVisible(has_results)
        self.empty.setVisible(not has_results)
        self.empty_hint.setVisible(not has_results)
        if self.mine and not has_results and not self.search.text():
            self.empty.setText("Здесь появятся ваши книги")
            self.empty_hint.setText("Нажмите «Новая книга», чтобы начать")
        else:
            self.empty.setText("Ничего не найдено")
            self.empty_hint.setText("Попробуйте изменить запрос или сбросить фильтры")
        self.count_label.setText(f"Книг: {len(items)}")

    def show_more(self):
        batch = self.items[self.shown:self.shown + PAGE_SIZE]
        cards = []
        for item in batch:
            card = BookCard(item)
            card.clicked.connect(self.window_ref.open_book)
            cards.append(card)
        self.shown += len(batch)
        self.grid.add_cards(cards)
        remaining = len(self.items) - self.shown
        self.more_button.setVisible(remaining > 0)
        self.more_button.setText(f"Показать ещё ({remaining})")

    def create_book(self):
        if can_write(self.window_ref.user):
            self.window_ref.edit_book(None)
