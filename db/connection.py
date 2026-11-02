"""
Database connection and session initialization.
"""
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

load_dotenv()

# If DATABASE_URL is set (e.g. a Supabase/Postgres URI), ensure it specifies the psycopg2 driver.
# In SQLAlchemy 2.0+, bare "postgresql://" attempts to load "psycopg" (version 3), which causes
# ModuleNotFoundError on environments with psycopg2-binary installed.
DB_PATH = os.getenv("DB_PATH", "tbe_workbench.db")
raw_db_url = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")
if raw_db_url.startswith("postgres://"):
    DATABASE_URL = raw_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif raw_db_url.startswith("postgresql://") and not raw_db_url.startswith("postgresql+"):
    DATABASE_URL = raw_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
else:
    DATABASE_URL = raw_db_url

IS_SQLITE = DATABASE_URL.startswith("sqlite")

# For SQLite: NullPool eliminates table lock ceilings.
# For PostgreSQL/Supabase: QueuePool keeps connections warm and reuses them,
# eliminating the costly 200ms TCP+TLS roundtrips on every single query.
if IS_SQLITE:
    engine = create_engine(
        DATABASE_URL,
        poolclass=NullPool,
        connect_args={
            "check_same_thread": False,
            "timeout": 60.0  # Wait up to 60s for lock to clear instead of failing immediately (default 5s)
        },
        echo=False
    )
else:
    engine = create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_recycle=1800,  # Recycle connections every 30 mins to prevent stale drops
        pool_pre_ping=True, # Auto-verify connection health before executing query
        echo=False
    )

if IS_SQLITE:
    # Enable foreign key support, WAL mode, and busy timeout for high concurrency in SQLite.
    # PRAGMA is SQLite-only syntax — Postgres has no equivalent and doesn't need one,
    # since it doesn't have SQLite's single-writer locking behavior this works around.
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=60000")  # 60,000ms (60 seconds) wait queue
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
    """Creates all tables defined in models and sets up the page-level full-text search table."""
    from db import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    with engine.connect() as conn:
        if IS_SQLITE:
            # SQLite FTS5 virtual table for page-level text search
            conn.exec_driver_sql("""
                CREATE VIRTUAL TABLE IF NOT EXISTS page_fts USING fts5(
                    page_id UNINDEXED,
                    document_id UNINDEXED,
                    page_number UNINDEXED,
                    content
                );
            """)
        else:
            # Postgres equivalent: a plain table with a generated tsvector column
            # + GIN index, queried via to_tsquery/ts_rank in reading/fts_indexer.py
            # instead of FTS5's MATCH/bm25() (Postgres has no fts5 module).
            conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS page_fts (
                    page_id INTEGER,
                    document_id INTEGER,
                    page_number INTEGER,
                    content TEXT,
                    content_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
                );
            """)
            conn.exec_driver_sql("""
                CREATE INDEX IF NOT EXISTS page_fts_tsv_idx ON page_fts USING GIN(content_tsv);
            """)
        conn.commit()

