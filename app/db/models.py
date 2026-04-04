from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint, Boolean
from datetime import datetime, timezone
from app.db.database import Base

class DownloadLink(Base):
    __tablename__ = "download_links"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True)
    hoster = Column(String)
    status = Column(String)
    filename = Column(String)
    size = Column(String, nullable=True)
    size_bytes = Column(Integer, nullable=True)
    last_checked = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    source_name = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    
    # Metadata extracted from filename
    title = Column(String, nullable=True) # Title extracted from file
    category = Column(String, nullable=True) # movie/series
    year = Column(Integer, nullable=True)
    season = Column(String, nullable=True)
    episode = Column(String, nullable=True)
    resolution = Column(String, nullable=True)
    quality = Column(String, nullable=True)
    codec = Column(String, nullable=True)
    language = Column(String, nullable=True)

class ScrapedURL(Base):
    __tablename__ = "scraped_urls"

    url = Column(String, primary_key=True)
    source_name = Column(String, index=True)
    last_scraped = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    status = Column(String, default="success") # 'success' or 'failed'
    scrape_once = Column(Boolean, default=False)
    duration_ms = Column(Integer, nullable=True)
