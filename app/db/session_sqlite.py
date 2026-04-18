"""SQLite session helper for local development/testing."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def get_sqlite_session(db_path: str = "test.db"):
    """Create a SQLite session."""
    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    return Session()


def get_sqlite_engine(db_path: str = "test.db"):
    """Create a SQLite engine."""
    return create_engine(f"sqlite:///{db_path}")
