import hashlib
import hmac
import secrets

from sqlalchemy import select

from app.config import ROLE_ADMIN, ROLE_AUTHOR, ROLE_READER, ROLES
from app.db import User
from app.services.books import refresh_author_books
from app.services.rules import (
    AuthError,
    DISPLAY_NAME_MAX,
    NotFound,
    PASSWORD_MAX,
    PASSWORD_MIN,
    require_admin,
    require_length,
    single_line,
    USERNAME_MAX,
    USERNAME_MIN,
    USERNAME_PATTERN,
    ValidationError,
)


ITERATIONS = 200_000


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS)
    return digest.hex(), salt


def verify_password(password, password_hash, salt):
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, password_hash)


MIN_PASSWORD_LENGTH = PASSWORD_MIN


def register(session, username, password, role=ROLE_READER, display_name=""):
    username = (username or "").strip()
    if not USERNAME_MIN <= len(username) <= USERNAME_MAX:
        raise ValidationError(f"Логин должен содержать от {USERNAME_MIN} до {USERNAME_MAX} символов")
    if not USERNAME_PATTERN.match(username):
        raise ValidationError("Логин может содержать только буквы, цифры, точку, дефис и подчёркивание")
    validate_password(password)
    display_name = require_length(single_line(display_name), DISPLAY_NAME_MAX, "Имя")
    if role not in (ROLE_READER, ROLE_AUTHOR):
        raise ValidationError("Можно зарегистрироваться только как читатель или автор")
    if session.scalar(select(User).where(User.username == username)):
        raise ValidationError("Пользователь с таким логином уже существует")
    return create_user(session, username, password, role, display_name)


def create_user(session, username, password, role, display_name=""):
    password_hash, salt = hash_password(password)
    user = User(
        username=username,
        display_name=(display_name or "").strip(),
        password_hash=password_hash,
        salt=salt,
        role=role,
    )
    session.add(user)
    session.flush()
    return user


def validate_password(password):
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"Пароль должен содержать не менее {MIN_PASSWORD_LENGTH} символов")
    if len(password) > PASSWORD_MAX:
        raise ValidationError(f"Пароль должен содержать не более {PASSWORD_MAX} символов")


def login(session, username, password):
    username = (username or "").strip()
    if len(username) > USERNAME_MAX or len(password or "") > PASSWORD_MAX:
        raise AuthError("Неверный логин или пароль")
    user = session.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(password or "", user.password_hash, user.salt):
        raise AuthError("Неверный логин или пароль")
    if user.is_blocked:
        raise AuthError("Учётная запись заблокирована администратором")
    return user


DEFAULT_ADMIN = ("admin", "admin123")


def ensure_admin(session):
    active = session.scalar(select(User).where(User.role == ROLE_ADMIN, User.is_blocked.is_(False)).limit(1))
    if active is not None:
        return active
    username, password = DEFAULT_ADMIN
    user = session.scalar(select(User).where(User.username == username))
    if user is None:
        return create_user(session, username, password, ROLE_ADMIN, "Администратор")
    user.role = ROLE_ADMIN
    user.is_blocked = False
    session.flush()
    return user


def list_users(session):
    return list(session.scalars(select(User).order_by(User.created_at, User.id)))


def get_user(session, user_id):
    user = session.get(User, user_id)
    if user is None:
        raise NotFound("Пользователь не найден")
    return user


def set_blocked(session, admin, user_id, blocked):
    require_admin(admin)
    user = get_user(session, user_id)
    if user.id == admin.id:
        raise ValidationError("Нельзя заблокировать самого себя")
    user.is_blocked = bool(blocked)
    session.flush()
    return user


def set_role(session, admin, user_id, role):
    require_admin(admin)
    if role not in ROLES:
        raise ValidationError("Неизвестная роль")
    user = get_user(session, user_id)
    if user.id == admin.id:
        raise ValidationError("Нельзя изменить собственную роль")
    user.role = role
    session.flush()
    return user


def update_profile(session, user_id, display_name, current_password="", new_password=""):
    user = get_user(session, user_id)
    display_name = single_line(display_name)
    if not display_name:
        raise ValidationError("Имя не может быть пустым")
    require_length(display_name, DISPLAY_NAME_MAX, "Имя")
    if new_password:
        if len(current_password or "") > PASSWORD_MAX or not verify_password(current_password or "", user.password_hash, user.salt):
            raise ValidationError("Текущий пароль указан неверно")
        validate_password(new_password)
        user.password_hash, user.salt = hash_password(new_password)
    name_changed = display_name != user.display_name
    user.display_name = display_name
    session.flush()
    if name_changed:
        refresh_author_books(session, user.id)
    return user
