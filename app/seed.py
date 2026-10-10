import json
import random
from datetime import datetime, timedelta

from app import db
from app.config import BOOK_FINISHED, ROLE_ADMIN, ROLE_AUTHOR, ROLE_READER, seed_dir, SHELF_PLANNED, SHELF_READING
from app.db import Chapter
from app.services import auth, books, reading


DEMO_READERS = (
    ("anna", "Анна Королёва"),
    ("mikhail", "Михаил Орлов"),
    ("olga", "Ольга Белова"),
    ("dmitry", "Дмитрий Соколов"),
)


def load_manifest():
    path = seed_dir() / "seed.json"
    if not path.exists():
        return {"genres": [], "books": []}
    return json.loads(path.read_text(encoding="utf-8"))


def seed(session, manifest=None, progress=None):
    manifest = manifest or load_manifest()
    report = progress or (lambda done, total, text: None)
    total = len(manifest.get("books", [])) + 1
    report(0, total, "Создание учётных записей")
    generator = random.Random(1837)
    for name in manifest.get("genres", []):
        books.ensure_genre(session, name)
    admin = auth.create_user(session, "admin", "admin123", ROLE_ADMIN, "Администратор")
    reader = auth.create_user(session, "reader", "reader123", ROLE_READER, "Читатель")
    voters = [reader, admin] + [auth.create_user(session, login, "reader123", ROLE_READER, name) for login, name in DEMO_READERS]
    authors = {}
    now = datetime.now()
    created = []
    for index, entry in enumerate(manifest.get("books", [])):
        report(index + 1, total, f"{entry['title']} — {entry['author']['name']}")
        author_info = entry["author"]
        author = authors.get(author_info["username"])
        if author is None:
            author = auth.create_user(session, author_info["username"], "author123", ROLE_AUTHOR, author_info["name"])
            authors[author_info["username"]] = author
        cover_name = None
        cover = entry.get("cover")
        if cover and (seed_dir() / cover["file"]).exists():
            cover_name = books.store_cover(seed_dir() / cover["file"])
        genre_ids = [books.ensure_genre(session, name).id for name in entry["genres"]]
        book = books.create_book(
            session, author, entry["title"], entry["description"], genre_ids, entry.get("status", BOOK_FINISHED), cover_name
        )
        moment = now - timedelta(days=len(manifest["books"]) - index, hours=generator.randint(0, 20))
        book.created_at = moment
        book.updated_at = moment
        book.views = generator.randint(40, 900)
        for number, chapter in enumerate(entry["chapters"], start=1):
            session.add(Chapter(book_id=book.id, number=number, title=chapter["title"], content=chapter["content"], created_at=moment))
        session.flush()
        created.append(book)
        bias = entry.get("rating_bias", 4)
        for voter in voters:
            if generator.random() < 0.75:
                value = max(1, min(5, bias + generator.choice((-1, 0, 0, 1))))
                books.rate(session, voter, book.id, value)
    if created:
        reading.set_status(session, reader, created[0].id, SHELF_READING)
        for book in created[1:3]:
            reading.set_status(session, reader, book.id, SHELF_PLANNED)
    session.flush()


def needs_seed():
    with db.session_scope() as session:
        return db.is_empty(session)


def seed_if_empty(progress=None):
    with db.session_scope() as session:
        if db.is_empty(session):
            seed(session, progress=progress)
        auth.ensure_admin(session)
