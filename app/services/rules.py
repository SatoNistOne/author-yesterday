import re

from app.config import ROLE_ADMIN, ROLE_AUTHOR


class ServiceError(Exception):
    pass


class ValidationError(ServiceError):
    pass


class AuthError(ServiceError):
    pass


class AccessDenied(ServiceError):
    pass


class NotFound(ServiceError):
    pass


USERNAME_MIN = 3
USERNAME_MAX = 32
DISPLAY_NAME_MAX = 64
PASSWORD_MIN = 6
PASSWORD_MAX = 128
TITLE_MAX = 255
DESCRIPTION_MAX = 5000
CHAPTER_TITLE_MAX = 255
CHAPTER_MAX = 500_000
GENRE_MAX = 64
SEARCH_MAX = 200
SEARCH_TERMS_MAX = 10
SCROLL_MAX = 10_000
IMAGE_FILE_MAX = 25 * 1024 * 1024
IMAGE_PIXELS_MAX = 60_000_000

USERNAME_PATTERN = re.compile(r"^[A-Za-zА-Яа-яЁё0-9_.\-]+$")
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def strip_control(text):
    return CONTROL_CHARS.sub("", text or "")


def single_line(text):
    return " ".join(strip_control(text).split())


def require_length(text, maximum, message):
    if len(text) > maximum:
        raise ValidationError(f"{message}: не более {maximum} символов")
    return text


def is_admin(user):
    return user is not None and user.role == ROLE_ADMIN


def can_write(user):
    return user is not None and user.role in (ROLE_AUTHOR, ROLE_ADMIN)


def can_edit_book(user, book):
    return is_admin(user) or (user is not None and user.role == ROLE_AUTHOR and book.author_id == user.id)


def require_admin(user):
    if not is_admin(user):
        raise AccessDenied("Действие доступно только администратору")


def require_book_editor(user, book):
    if not can_edit_book(user, book):
        raise AccessDenied("Нет прав на изменение этой книги")
