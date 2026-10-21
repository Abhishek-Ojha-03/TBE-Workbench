"""
Database connection and session initialization.
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "tbe_workbench.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Needed for SQLite + Streamlit concurrency
    echo=False
)

# Enable foreign key support in SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Context manager or generator for database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Creates all tables defined in models and sets up FTS5 full-text table."""
    from db import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    
    # Initialize SQLite FTS5 table for page-level text search
    with engine.connect() as conn:
        conn.exec_driver_sql("""
            CREATE VIRTUAL TABLE IF NOT EXISTS page_fts USING fts5(
                page_id UNINDEXED,
                document_id UNINDEXED,
                page_number UNINDEXED,
                content
            );
        """)
        conn.commit()

