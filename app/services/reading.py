from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.config import SHELF_READING, SHELF_STATUSES
from app.db import Book, Chapter, LibraryEntry
from app.services.books import get_book
from app.services.rules import (
    CHAPTER_MAX,
    CHAPTER_TITLE_MAX,
    NotFound,
    require_book_editor,
    require_length,
    SCROLL_MAX,
    single_line,
    strip_control,
    ValidationError,
)


def list_chapters(session, book_id):
    return list(session.scalars(select(Chapter).where(Chapter.book_id == book_id).order_by(Chapter.number)))


def get_chapter(session, chapter_id):
    chapter = session.get(Chapter, chapter_id)
    if chapter is None:
        raise NotFound("Глава не найдена")
    return chapter


def _validate(title, content):
    title = single_line(title)
    content = strip_control(content).strip()
    if not title:
        raise ValidationError("Укажите название главы")
    if not content:
        raise ValidationError("Текст главы не может быть пустым")
    require_length(title, CHAPTER_TITLE_MAX, "Название главы")
    require_length(content, CHAPTER_MAX, "Текст главы")
    return title, content


def add_chapter(session, user, book_id, title, content):
    book = get_book(session, book_id)
    require_book_editor(user, book)
    title, content = _validate(title, content)
    last_number = session.scalar(select(func.max(Chapter.number)).where(Chapter.book_id == book_id)) or 0
    chapter = Chapter(book_id=book_id, number=last_number + 1, title=title, content=content)
    session.add(chapter)
    book.updated_at = datetime.now()
    session.flush()
    return chapter


def update_chapter(session, user, chapter_id, title, content):
    chapter = get_chapter(session, chapter_id)
    require_book_editor(user, chapter.book)
    chapter.title, chapter.content = _validate(title, content)
    session.flush()
    return chapter


def delete_chapter(session, user, chapter_id):
    chapter = get_chapter(session, chapter_id)
    book_id = chapter.book_id
    require_book_editor(user, chapter.book)
    session.delete(chapter)
    session.flush()
    _renumber(session, book_id)


def move_chapter(session, user, chapter_id, offset):
    chapter = get_chapter(session, chapter_id)
    require_book_editor(user, chapter.book)
    chapters = list_chapters(session, chapter.book_id)
    index = chapters.index(chapter)
    target = index + offset
    if target < 0 or target >= len(chapters):
        return chapter
    chapters[index], chapters[target] = chapters[target], chapters[index]
    for number, item in enumerate(chapters, start=1):
        item.number = number
    session.flush()
    return chapter


def _renumber(session, book_id):
    for number, chapter in enumerate(list_chapters(session, book_id), start=1):
        chapter.number = number
    session.flush()


def neighbours(session, chapter):
    chapters = list_chapters(session, chapter.book_id)
    index = [item.id for item in chapters].index(chapter.id)
    previous = chapters[index - 1] if index > 0 else None
    following = chapters[index + 1] if index + 1 < len(chapters) else None
    return previous, following


def get_entry(session, user, book_id):
    return session.scalar(select(LibraryEntry).where(LibraryEntry.user_id == user.id, LibraryEntry.book_id == book_id))


def set_status(session, user, book_id, status):
    if status not in SHELF_STATUSES:
        raise ValidationError("Неизвестный статус полки")
    get_book(session, book_id)
    entry = get_entry(session, user, book_id)
    if entry is None:
        entry = LibraryEntry(user_id=user.id, book_id=book_id, status=status)
        session.add(entry)
    else:
        entry.status = status
    session.flush()
    return entry


def remove(session, user, book_id):
    entry = get_entry(session, user, book_id)
    if entry is not None:
        session.delete(entry)
        session.flush()


def list_entries(session, user, status=None):
    statement = (
        select(LibraryEntry)
        .where(LibraryEntry.user_id == user.id)
        .options(selectinload(LibraryEntry.book).selectinload(Book.author), selectinload(LibraryEntry.book).selectinload(Book.genres))
        .order_by(LibraryEntry.updated_at.desc())
    )
    if status:
        statement = statement.where(LibraryEntry.status == status)
    return list(session.scalars(statement))


def save_position(session, user, book_id, chapter_id, scroll_pos):
    entry = get_entry(session, user, book_id)
    if entry is None:
        entry = LibraryEntry(user_id=user.id, book_id=book_id, status=SHELF_READING)
        session.add(entry)
    entry.last_chapter_id = chapter_id
    entry.scroll_pos = min(SCROLL_MAX, max(0, int(scroll_pos)))
    session.flush()
    return entry


def get_position(session, user, book_id):
    entry = get_entry(session, user, book_id)
    if entry is None or entry.last_chapter_id is None:
        return None, 0
    if session.get(Chapter, entry.last_chapter_id) is None:
        return None, 0
    return entry.last_chapter_id, entry.scroll_pos


@dataclass
class ShelfRow:
    entry: LibraryEntry
    chapter_number: int | None
    chapter_title: str | None
    total_chapters: int


def shelf_rows(session, user, status=None):
    rows = []
    for entry in list_entries(session, user, status):
        total = session.scalar(select(func.count(Chapter.id)).where(Chapter.book_id == entry.book_id)) or 0
        chapter = session.get(Chapter, entry.last_chapter_id) if entry.last_chapter_id else None
        rows.append(ShelfRow(entry, chapter.number if chapter else None, chapter.title if chapter else None, total))
    return rows


def last_read(session, user):
    statement = (
        select(LibraryEntry)
        .where(LibraryEntry.user_id == user.id, LibraryEntry.last_chapter_id.is_not(None))
        .order_by(LibraryEntry.updated_at.desc())
        .limit(1)
    )
    entry = session.scalar(statement)
    if entry is None:
        return None
    return next((row for row in shelf_rows(session, user) if row.entry.id == entry.id), None)


def counts(session, user):
    statement = select(LibraryEntry.status, func.count(LibraryEntry.id)).where(LibraryEntry.user_id == user.id).group_by(LibraryEntry.status)
    return dict(session.execute(statement).all())
