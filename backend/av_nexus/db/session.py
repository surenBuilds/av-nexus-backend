"""Database engine + session management.

Default is SQLite (offline dev/tests). Set AVNEXUS_DB_URL to a PostgreSQL DSN for
production. SQLAlchemy 2.0 typing is used throughout.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from av_nexus.config import settings

_engine_kwargs: dict[str, object] = {}
if settings.db_url.startswith("sqlite"):
    path = settings.db_url.replace("sqlite:///", "")
    if path and path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    _engine_kwargs = {"connect_args": {"check_same_thread": False}}

_engine: Engine = create_engine(settings.db_url, echo=settings.db_echo, **_engine_kwargs)
_SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)


def get_engine() -> Engine:
    return _engine


def create_session() -> Session:
    return _SessionLocal()


def get_session() -> Generator[Session]:
    """FastAPI dependency: yield a session, close it afterwards."""
    session = create_session()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Create tables from SQLAlchemy metadata (dev/simplified migrations)."""
    import av_nexus.models as models  # noqa: F401  (registers all tables on metadata)

    models.base.Base.metadata.create_all(bind=_engine)
