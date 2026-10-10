from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QVBoxLayout,
)

from app import db
from app.config import BOOK_IN_PROGRESS, BOOK_STATUSES
from app.services import books, reading
from app.services.rules import CHAPTER_MAX, DESCRIPTION_MAX, ValidationError
from app.ui import theme
from app.ui.common import button, fit_to_screen, guarded, label
from app.ui.widgets import CoverLabel


IMAGE_FILTER = "Изображения (*.png *.jpg *.jpeg *.webp *.bmp)"


class BookEditor(QDialog):
    def __init__(self, user, book_id=None, parent=None):
        super().__init__(parent)
        self.user = user
        self.book_id = book_id
        self.new_cover_file = None
        self.saved_book_id = None
        self.setWindowTitle("Редактирование книги" if book_id else "Новая книга")
        fit_to_screen(self, 820, 620)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(26)

        cover_column = QVBoxLayout()
        self.cover = CoverLabel(200, 300, 10)
        cover_column.addWidget(self.cover)
        cover_column.addWidget(button("Выбрать обложку…", None, self.choose_cover))
        cover_column.addWidget(label("Изображение будет обрезано до 400×600", "Muted", wrap=True))
        cover_column.addStretch()
        layout.addLayout(cover_column)

        form_column = QVBoxLayout()
        form_column.addWidget(label("Новая книга" if not book_id else "Редактирование", "SectionTitle"))
        form = QFormLayout()
        form.setVerticalSpacing(12)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Обязательное поле")
        self.title_edit.setMaxLength(255)
        self.title_edit.textChanged.connect(self._refresh_placeholder)
        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText("Коротко о чём книга — обязательное поле")
        self.description_counter = label("", "Muted")
        self.description_edit.textChanged.connect(self._update_counter)
        self.status_combo = QComboBox()
        for status in BOOK_STATUSES:
            self.status_combo.addItem(status.capitalize(), status)
        self.genre_list = QListWidget()
        self.genre_list.setMaximumHeight(170)
        form.addRow("Название", self.title_edit)
        form.addRow("Описание", self.description_edit)
        form.addRow("", self.description_counter)
        form.addRow("Статус", self.status_combo)
        form.addRow("Жанры", self.genre_list)
        form_column.addLayout(form, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button("Отмена", None, self.reject))
        actions.addWidget(button("Сохранить", "primary", self.save))
        form_column.addLayout(actions)
        layout.addLayout(form_column, 1)

        self.existing_cover = None
        self.author_name = user.name
        self._load()

    def _load(self):
        with db.session_scope() as session:
            all_genres = [(genre.id, genre.name) for genre in books.list_genres(session)]
            selected = set()
            if self.book_id:
                book = books.get_book(session, self.book_id)
                self.title_edit.setText(book.title)
                self.description_edit.setPlainText(book.description)
                self.status_combo.setCurrentIndex(self.status_combo.findData(book.status))
                selected = {genre.id for genre in book.genres}
                self.existing_cover = book.cover_path
                self.author_name = book.author.name
            else:
                self.status_combo.setCurrentIndex(self.status_combo.findData(BOOK_IN_PROGRESS))
                self.author_name = self.user.name
        for genre_id, name in all_genres:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, genre_id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if genre_id in selected else Qt.CheckState.Unchecked)
            self.genre_list.addItem(item)
        self._refresh_placeholder()

    def _update_counter(self):
        length = len(self.description_edit.toPlainText())
        self.description_counter.setText(f"{length} / {DESCRIPTION_MAX}")
        self.description_counter.setObjectName("ErrorText" if length > DESCRIPTION_MAX else "Muted")
        self.description_counter.style().unpolish(self.description_counter)
        self.description_counter.style().polish(self.description_counter)

    def _refresh_placeholder(self):
        if self.new_cover_file:
            self.cover.set_image_file(self.new_cover_file)
        else:
            self.cover.set_cover(self.existing_cover, self.title_edit.text() or "Без названия", self.author_name)

    def selected_genres(self):
        return [
            self.genre_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.genre_list.count())
            if self.genre_list.item(row).checkState() == Qt.CheckState.Checked
        ]

    def choose_cover(self):
        path, _filter = QFileDialog.getOpenFileName(self, "Выбор обложки", str(Path.home()), IMAGE_FILTER)
        if path:
            self.new_cover_file = path
            self._refresh_placeholder()

    @guarded
    def save(self):
        if not self.title_edit.text().strip():
            raise ValidationError("Укажите название книги")
        if not self.description_edit.toPlainText().strip():
            raise ValidationError("Добавьте описание книги")
        if not self.selected_genres():
            raise ValidationError("Выберите хотя бы один жанр")
        stored_cover = books.store_cover(self.new_cover_file) if self.new_cover_file else None
        try:
            with db.session_scope() as session:
                arguments = (
                    self.title_edit.text(),
                    self.description_edit.toPlainText(),
                    self.selected_genres(),
                    self.status_combo.currentData(),
                    stored_cover,
                )
                if self.book_id:
                    book = books.update_book(session, self.user, self.book_id, *arguments)
                else:
                    book = books.create_book(session, self.user, *arguments)
                self.saved_book_id = book.id
        except Exception:
            books.remove_cover_file(stored_cover)
            raise
        self.accept()


class ChapterEditor(QDialog):
    def __init__(self, user, book_id, chapter_id=None, parent=None):
        super().__init__(parent)
        self.user = user
        self.book_id = book_id
        self.chapter_id = chapter_id
        self.setWindowTitle("Редактирование главы" if chapter_id else "Новая глава")
        fit_to_screen(self, 900, 700)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(12)
        layout.addWidget(label("Редактирование главы" if chapter_id else "Новая глава", "SectionTitle"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Название главы")
        self.title_edit.setMaxLength(255)
        layout.addWidget(self.title_edit)
        self.content_edit = QPlainTextEdit()
        self.content_edit.setPlaceholderText("Текст главы. Абзацы разделяйте пустой строкой.")
        self.content_edit.setFont(theme.serif_font(13))
        layout.addWidget(self.content_edit, 1)
        footer = QHBoxLayout()
        self.counter = label("", "Muted")
        self.content_edit.textChanged.connect(self._update_counter)
        footer.addWidget(self.counter)
        footer.addStretch()
        footer.addWidget(button("Отмена", None, self.reject))
        footer.addWidget(button("Сохранить", "primary", self.save))
        layout.addLayout(footer)
        if chapter_id:
            with db.session_scope() as session:
                chapter = reading.get_chapter(session, chapter_id)
                self.title_edit.setText(chapter.title)
                self.content_edit.setPlainText(chapter.content)
        self._update_counter()

    def _update_counter(self):
        text = self.content_edit.toPlainText()
        self.counter.setText(f"Слов: {len(text.split())} · знаков: {len(text)} из {CHAPTER_MAX}")
        self.counter.setObjectName("ErrorText" if len(text) > CHAPTER_MAX else "Muted")
        self.counter.style().unpolish(self.counter)
        self.counter.style().polish(self.counter)

    @guarded
    def save(self):
        if not self.title_edit.text().strip():
            raise ValidationError("Укажите название главы")
        if not self.content_edit.toPlainText().strip():
            raise ValidationError("Текст главы не может быть пустым")
        with db.session_scope() as session:
            if self.chapter_id:
                reading.update_chapter(session, self.user, self.chapter_id, self.title_edit.text(), self.content_edit.toPlainText())
            else:
                reading.add_chapter(session, self.user, self.book_id, self.title_edit.text(), self.content_edit.toPlainText())
        self.accept()
