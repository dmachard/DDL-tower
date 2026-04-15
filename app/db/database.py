from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import event
from app.core.config import settings
import os

# Create data directory if it doesn't exist
os.makedirs("./data", exist_ok=True)

DATABASE_URL = settings.DATABASE_URL

# Connect arguments for SQLite busy_timeout (30 seconds)
connect_args = {"timeout": 30}

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
    cursor.close()

AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session

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
        
        await conn.run_sync(migrate)
