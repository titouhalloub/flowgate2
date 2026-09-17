"""Database engine and session management (SQLAlchemy 2.0 style)."""

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _writable_dir(path: Path) -> bool:
    """True if we can create files under *path* (creates it if missing)."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.touch()
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _resolve_sqlite_url(url: str) -> str:
    """Return a bootable SQLite URL, falling back to ephemeral storage.

    The configured URL (e.g. sqlite:////var/data/a27.db) requires its
    parent dir to exist *and* be writable -- on Render free tier /var is
    read-only without an attached disk, so mkdir raises PermissionError.
    Instead of crashing the deploy, fall back to ./a27.db (ephemeral:
    the app boots and works, data is lost on redeploy). A persistent
    disk or Postgres is still the right answer for real data.
    """
    if not url.startswith("sqlite:"):
        return url
    raw = url.split(":///", 1)[-1].split("?", 1)[0].strip()
    if not raw or raw == ":memory:":
        return url
    if _writable_dir(Path(raw).expanduser().parent):
        return url
    fallback = "sqlite:///./a27.db"
    print(
        f"WARNING: sqlite path {raw!r} is not writable; "
        f"falling back to ephemeral {fallback} (data will not persist)."
    )
    return fallback


settings.database_url = _resolve_sqlite_url(settings.database_url)
_db_url = settings.database_url
_engine_kwargs: dict = {"future": True}

if _db_url.startswith("postgresql"):
    # Neon (and other serverless Postgres) suspend compute when idle. The
    # first connection after a cold start can hit a dead socket; without
    # pool_pre_ping the dead connection is handed to the caller and the
    # request 500s. pre_ping tests the connection before use and transparently
    # reconnects if dead. pool_recycle caps connection lifetime below Neon's
    # idle cutoff so stale sockets do not accumulate. connect_timeout caps
    # the wake-up wait so a slow cold start becomes a fast failure rather
    # than a hung request.
    _engine_kwargs.update(
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": 10},
    )

engine = create_engine(_db_url, **_engine_kwargs)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):
    # SQLite ships with FK enforcement OFF by default; turn it on so the
    # test suite catches INSERT-ordering bugs the way Postgres does.
    import sqlite3
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


def init_db() -> None:
    """Create all tables. Used by tests and dev bootstrap; production uses Alembic."""
    from app import models  # ensure models are imported before create_all

    Base.metadata.create_all(bind=engine)