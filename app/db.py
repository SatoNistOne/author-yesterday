from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    create_engine,
    DateTime,
    event,
    ForeignKey,
    Integer,
    select,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import BOOK_IN_PROGRESS, database_url, ROLE_READER, SHELF_PLANNED


engine = None
SessionFactory = sessionmaker(expire_on_commit=False)


def _enable_foreign_keys(dbapi_connection, _record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def make_engine(url=None):
    url = url or database_url()
    options = {}
    if url.endswith(":memory:") or url == "sqlite://":
        options = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    new_engine = create_engine(url, **options)
    event.listen(new_engine, "connect", _enable_foreign_keys)
    return new_engine


SCHEMA_VERSION = 1
MIGRATIONS = {
    "users": {"display_name": "VARCHAR(128) NOT NULL DEFAULT ''"},
    "library_entries": {"updated_at": "DATETIME"},
}


def migrate(connection):
    version = connection.exec_driver_sql("PRAGMA user_version").scalar()
    if version >= SCHEMA_VERSION:
        return
    for table, columns in MIGRATIONS.items():
        existing = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})")}
        for column, definition in columns.items():
            if column not in existing:
                connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    connection.exec_driver_sql(f"PRAGMA user_version = {SCHEMA_VERSION}")


def init_db(url=None):
    global engine
    engine = make_engine(url)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        migrate(connection)
    SessionFactory.configure(bind=engine)
    return engine


@contextmanager
def session_scope():
    session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def is_empty(session):
    return session.scalar(select(User.id).limit(1)) is None


class Base(DeclarativeBase):
    pass


book_genres = Table(
    "book_genres",
    Base.metadata,
    Column("book_id", ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(128))
    salt: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(16), default=ROLE_READER)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    books: Mapped[list["Book"]] = relationship(back_populates="author", cascade="all, delete-orphan", passive_deletes=True)

    @property
    def name(self):
        return self.display_name or self.username


class Genre(Base):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    cover_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=BOOK_IN_PROGRESS)
    views: Mapped[int] = mapped_column(Integer, default=0)
    search_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    author: Mapped[User] = relationship(back_populates="books")
    genres: Mapped[list[Genre]] = relationship(secondary=book_genres, order_by=Genre.name)
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="book", cascade="all, delete-orphan", passive_deletes=True, order_by="Chapter.number"
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    book: Mapped[Book] = relationship(back_populates="chapters")


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id"),
        CheckConstraint("value BETWEEN 1 AND 5"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"))
    value: Mapped[int] = mapped_column(Integer)


class LibraryEntry(Base):
    __tablename__ = "library_entries"
    __table_args__ = (UniqueConstraint("user_id", "book_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(32), default=SHELF_PLANNED)
    last_chapter_id: Mapped[int | None] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)
    scroll_pos: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    book: Mapped[Book] = relationship()
