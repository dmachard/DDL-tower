from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from contextlib import asynccontextmanager
from app.core.config import settings
import os
import asyncio

# Create data directory if it doesn't exist
os.makedirs("./data", exist_ok=True)

DATABASE_URL = settings.DATABASE_URL

# Connect arguments for SQLite busy_timeout (60 seconds)
connect_args = {
    "timeout": 60,
    "check_same_thread": False
}

engine = create_async_engine(
    DATABASE_URL, 
    echo=False, 
    connect_args=connect_args
)

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA cache_size=-64000")  # 64MB cache
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA mmap_size=268435456") # 256MB mmap
    cursor.close()

@event.listens_for(engine.sync_engine, "begin")
def do_begin(conn):
    # This forces a write lock at the start of the transaction 
    # to avoid 'database is locked' during concurrent writes
    conn.exec_driver_sql("BEGIN IMMEDIATE")

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    """Provides a transactional database session with retry logic for SQLite locks."""
    max_retries = 5
    retry_delay = 2
    
    for attempt in range(max_retries):
        async with AsyncSessionLocal() as session:
            try:
                # BEGIN IMMEDIATE is already handled by the @event listener
                yield session
                await session.commit()
                return # Success
            except OperationalError as e:
                await session.rollback()
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    print(f"[DB] Database is locked, retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                    continue
                raise
            except (GeneratorExit, asyncio.CancelledError):
                # Critical: do not retry if the generator is being closed or task cancelled
                await session.rollback()
                raise
            except Exception:
                await session.rollback()
                raise

get_db_ctx = asynccontextmanager(get_db)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Lightweight migrations for existing tables
    async with engine.connect() as conn:
        def migrate(sync_conn):
            # Add rating column if it doesn't exist
            inspector = sync_conn.connection.cursor()
            inspector.execute("PRAGMA table_info(media_metadata)")
            columns = [col[1] for col in inspector.fetchall()]
            if columns and "rating" not in columns:
                print("[DB] Migration: Adding 'rating' column to 'media_metadata' table")
                sync_conn.connection.execute("ALTER TABLE media_metadata ADD COLUMN rating TEXT")
            
            if columns and "title_fr" not in columns:
                print("[DB] Migration: Adding 'title_fr' column to 'media_metadata' table")
                sync_conn.connection.execute("ALTER TABLE media_metadata ADD COLUMN title_fr TEXT")

            # Add network column to download_links
            inspector.execute("PRAGMA table_info(download_links)")
            dl_columns = [col[1] for col in inspector.fetchall()]
            if dl_columns and "network" not in dl_columns:
                print("[DB] Migration: Adding 'network' column to 'download_links' table")
                sync_conn.connection.execute("ALTER TABLE download_links ADD COLUMN network TEXT")
            
            if dl_columns and "v_quality" not in dl_columns:
                print("[DB] Migration: Adding 'v_quality' column to 'download_links' table")
                sync_conn.connection.execute("ALTER TABLE download_links ADD COLUMN v_quality TEXT")
            
            if dl_columns and "raw_title" not in dl_columns:
                print("[DB] Migration: Adding 'raw_title' column to 'download_links' table")
                sync_conn.connection.execute("ALTER TABLE download_links ADD COLUMN raw_title TEXT")
        
        await conn.run_sync(migrate)
