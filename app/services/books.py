import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.config import BOOK_STATUSES, COVER_SIZE, covers_dir, SORT_NEW, SORT_POPULAR, SORT_RATING, SORT_TITLE
from app.db import Book, book_genres, Genre, Rating
from app.services.rules import (
    AccessDenied,
    can_write,
    DESCRIPTION_MAX,
    GENRE_MAX,
    IMAGE_FILE_MAX,
    IMAGE_PIXELS_MAX,
    NotFound,
    require_admin,
    require_book_editor,
    require_length,
    SEARCH_MAX,
    SEARCH_TERMS_MAX,
    ServiceError,
    single_line,
    strip_control,
    TITLE_MAX,
    ValidationError,
)


@dataclass
class BookItem:
    book: Book
    rating: float
    votes: int


def build_search_text(title, author_name, description):
    return " ".join(part for part in (title, author_name, description) if part).casefold()


def _rating_subquery():
    return (
        select(
            Rating.book_id.label("book_id"),
            func.avg(Rating.value).label("avg_value"),
            func.count(Rating.id).label("votes"),
        )
        .group_by(Rating.book_id)
        .subquery()
    )


def _load_options():
    return (selectinload(Book.author), selectinload(Book.genres))


def search_books(session, query="", genre_ids=None, status=None, min_rating=0, sort=SORT_NEW, author_id=None):
    ratings = _rating_subquery()
    average = func.coalesce(ratings.c.avg_value, 0)
    votes = func.coalesce(ratings.c.votes, 0)
    statement = (
        select(Book, average, votes)
        .outerjoin(ratings, ratings.c.book_id == Book.id)
        .options(*_load_options())
    )
    for term in (query or "")[:SEARCH_MAX].casefold().split()[:SEARCH_TERMS_MAX]:
        statement = statement.where(Book.search_text.contains(term, autoescape=True))
    if genre_ids:
        matching = select(book_genres.c.book_id).where(book_genres.c.genre_id.in_(list(genre_ids)))
        statement = statement.where(Book.id.in_(matching))
    if status:
        statement = statement.where(Book.status == status)
    if min_rating:
        statement = statement.where(average >= min_rating)
    if author_id is not None:
        statement = statement.where(Book.author_id == author_id)
    order = {
        SORT_NEW: (Book.created_at.desc(), Book.id.desc()),
        SORT_RATING: (average.desc(), votes.desc(), Book.title),
        SORT_POPULAR: (Book.views.desc(), Book.title),
        SORT_TITLE: (Book.title,),
    }.get(sort, (Book.created_at.desc(),))
    statement = statement.order_by(*order)
    return [BookItem(book, float(avg), int(count)) for book, avg, count in session.execute(statement)]


def get_book(session, book_id):
    book = session.scalar(
        select(Book).where(Book.id == book_id).options(*_load_options(), selectinload(Book.chapters))
    )
    if book is None:
        raise NotFound("Книга не найдена")
    return book


def register_view(session, book_id):
    book = get_book(session, book_id)
    book.views += 1
    session.flush()
    return book


def _validate(title, description, status):
    title = single_line(title)
    description = strip_control(description).strip()
    if not title:
        raise ValidationError("Укажите название книги")
    if len(title) > TITLE_MAX:
        raise ValidationError("Название слишком длинное")
    if not description:
        raise ValidationError("Добавьте описание книги")
    require_length(description, DESCRIPTION_MAX, "Описание")
    if status not in BOOK_STATUSES:
        raise ValidationError("Неизвестный статус книги")
    return title, description


def _genres_by_ids(session, genre_ids):
    genre_ids = set(genre_ids or [])
    if not genre_ids:
        raise ValidationError("Выберите хотя бы один жанр")
    found = list(session.scalars(select(Genre).where(Genre.id.in_(genre_ids))))
    if len(found) != len(genre_ids):
        raise ValidationError("Один из выбранных жанров был удалён, обновите список")
    return found


def refresh_search_text(book):
    book.search_text = build_search_text(book.title, book.author.name if book.author else "", book.description)


def create_book(session, user, title, description, genre_ids, status, cover_path=None, author=None):
    if not can_write(user):
        raise AccessDenied("Создавать книги могут только авторы")
    title, description = _validate(title, description, status)
    book = Book(
        author=author or user,
        title=title,
        description=description,
        status=status,
        cover_path=cover_path,
        genres=_genres_by_ids(session, genre_ids),
    )
    refresh_search_text(book)
    session.add(book)
    session.flush()
    return book


def update_book(session, user, book_id, title, description, genre_ids, status, cover_path=None):
    book = get_book(session, book_id)
    require_book_editor(user, book)
    title, description = _validate(title, description, status)
    book.title = title
    book.description = description
    book.status = status
    book.genres = _genres_by_ids(session, genre_ids)
    if cover_path and cover_path != book.cover_path:
        remove_cover_file(book.cover_path)
        book.cover_path = cover_path
    refresh_search_text(book)
    session.flush()
    return book


def delete_book(session, user, book_id):
    book = get_book(session, book_id)
    require_book_editor(user, book)
    cover = book.cover_path
    session.delete(book)
    session.flush()
    remove_cover_file(cover)


def refresh_author_books(session, user_id):
    for book in session.scalars(select(Book).where(Book.author_id == user_id).options(selectinload(Book.author))):
        refresh_search_text(book)
    session.flush()


def store_cover(source_path):
    try:
        if Path(source_path).stat().st_size > IMAGE_FILE_MAX:
            raise ServiceError(f"Файл обложки слишком большой: не более {IMAGE_FILE_MAX // 1024 // 1024} МБ")
        with Image.open(source_path) as image:
            if image.width * image.height > IMAGE_PIXELS_MAX:
                raise ServiceError("Изображение слишком большое по размеру в пикселях")
            image.draft("RGB", (COVER_SIZE[0] * 2, COVER_SIZE[1] * 2))
            image = ImageOps.exif_transpose(image).convert("RGB")
            image = ImageOps.fit(image, COVER_SIZE, Image.Resampling.LANCZOS)
            name = f"{uuid.uuid4().hex}.jpg"
            image.save(covers_dir() / name, "JPEG", quality=88)
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise ServiceError("Не удалось открыть изображение: файл повреждён, слишком велик или не является картинкой") from error
    return name


def cover_file(cover_path):
    if not cover_path:
        return None
    path = covers_dir() / cover_path
    return path if path.exists() else None


def remove_cover_file(cover_path):
    path = cover_file(cover_path)
    if path is not None:
        Path(path).unlink(missing_ok=True)


def list_genres(session):
    return list(session.scalars(select(Genre).order_by(Genre.name)))


def genres_with_books(session):
    counts = dict(
        session.execute(select(book_genres.c.genre_id, func.count(book_genres.c.book_id)).group_by(book_genres.c.genre_id)).all()
    )
    return [(genre, counts.get(genre.id, 0)) for genre in list_genres(session)]


def _validated_name(session, name, exclude_id=None):
    name = single_line(name)
    if not name:
        raise ValidationError("Название жанра не может быть пустым")
    require_length(name, GENRE_MAX, "Название жанра")
    existing = session.scalar(select(Genre).where(Genre.name == name))
    if existing and existing.id != exclude_id:
        raise ValidationError("Такой жанр уже существует")
    return name


def create_genre(session, user, name):
    require_admin(user)
    genre = Genre(name=_validated_name(session, name))
    session.add(genre)
    session.flush()
    return genre


def ensure_genre(session, name):
    genre = session.scalar(select(Genre).where(Genre.name == name))
    if genre is None:
        genre = Genre(name=name)
        session.add(genre)
        session.flush()
    return genre


def rename_genre(session, user, genre_id, name):
    require_admin(user)
    genre = session.get(Genre, genre_id)
    if genre is None:
        raise NotFound("Жанр не найден")
    genre.name = _validated_name(session, name, genre.id)
    session.flush()
    return genre


def delete_genre(session, user, genre_id):
    require_admin(user)
    genre = session.get(Genre, genre_id)
    if genre is None:
        raise NotFound("Жанр не найден")
    session.delete(genre)
    session.flush()


def rate(session, user, book_id, value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValidationError("Оценка должна быть числом от 1 до 5") from None
    if not 1 <= value <= 5:
        raise ValidationError("Оценка должна быть от 1 до 5")
    get_book(session, book_id)
    rating = session.scalar(select(Rating).where(Rating.user_id == user.id, Rating.book_id == book_id))
    if rating is None:
        rating = Rating(user_id=user.id, book_id=book_id, value=int(value))
        session.add(rating)
    else:
        rating.value = int(value)
    session.flush()
    return rating


def user_rating(session, user, book_id):
    return session.scalar(select(Rating.value).where(Rating.user_id == user.id, Rating.book_id == book_id))


def average(session, book_id):
    avg_value, votes = session.execute(
        select(func.avg(Rating.value), func.count(Rating.id)).where(Rating.book_id == book_id)
    ).one()
    return float(avg_value or 0), int(votes)
