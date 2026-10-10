import logging
import os
import sys
from pathlib import Path

from platformdirs import user_data_dir

APP_NAME = "Author Yesterday"
APP_SLUG = "AuthorYesterday"

ROLE_READER = "reader"
ROLE_AUTHOR = "author"
ROLE_ADMIN = "admin"
ROLES = (ROLE_READER, ROLE_AUTHOR, ROLE_ADMIN)
ROLE_TITLES = {ROLE_READER: "Читатель", ROLE_AUTHOR: "Автор", ROLE_ADMIN: "Администратор"}

BOOK_IN_PROGRESS = "в процессе"
BOOK_FINISHED = "завершена"
BOOK_STATUSES = (BOOK_IN_PROGRESS, BOOK_FINISHED)

SHELF_READING = "читаю"
SHELF_DONE = "прочитано"
SHELF_PLANNED = "в планах"
SHELF_STATUSES = (SHELF_READING, SHELF_PLANNED, SHELF_DONE)

SORT_NEW = "new"
SORT_RATING = "rating"
SORT_POPULAR = "popular"
SORT_TITLE = "title"
SORT_TITLES = {
    SORT_NEW: "Сначала новые",
    SORT_RATING: "По рейтингу",
    SORT_POPULAR: "По популярности",
    SORT_TITLE: "По названию",
}

COVER_SIZE = (400, 600)
WINDOW_SIZE = (1280, 800)
SEARCH_DEBOUNCE_MS = 300


def resource_dir():
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parent.parent


def assets_dir():
    return resource_dir() / "assets"


def fonts_dir():
    return assets_dir() / "fonts"


def seed_dir():
    return assets_dir() / "seed"


def data_dir():
    override = os.environ.get("AUTHOR_YESTERDAY_DATA")
    path = Path(override) if override else Path(user_data_dir(APP_SLUG, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def covers_dir():
    path = data_dir() / "covers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_path():
    return data_dir() / "author_yesterday.log"


def setup_logging():
    from logging.handlers import RotatingFileHandler

    handler = RotatingFileHandler(log_path(), maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None:
        root.addHandler(logging.StreamHandler())


def database_url():
    return f"sqlite:///{data_dir() / 'library.db'}"
