from sqlalchemy.orm import relationship
from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint, Boolean, ForeignKey
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
    title = Column(String, nullable=True) # Enriched title
    raw_title = Column(String, nullable=True) # Original scraper/feed title
    category = Column(String, nullable=True) # movie/series
    year = Column(Integer, nullable=True)
    season = Column(String, nullable=True)
    episode = Column(String, nullable=True)
    resolution = Column(String, nullable=True)
    quality = Column(String, nullable=True)
    codec = Column(String, nullable=True)
    language = Column(String, nullable=True)
    network = Column(String, nullable=True)
    v_quality = Column(String, nullable=True)
    audio = Column(String, nullable=True)
    channels = Column(String, nullable=True)

    # Reference to centralized metadata
    imdb_id = Column(String, ForeignKey("media_metadata.imdb_id"), nullable=True)
    metadata_rel = relationship("MediaMetadata", back_populates="links")

class MediaMetadata(Base):
    __tablename__ = "media_metadata"

    imdb_id = Column(String, primary_key=True) # Unique identifier (IMDb ID)
    official_title = Column(String, nullable=True)
    title_fr = Column(String, nullable=True)
    year = Column(Integer, nullable=True)
    poster_path = Column(String, nullable=True)
    plot_en = Column(String, nullable=True)
    plot_fr = Column(String, nullable=True)
    rating = Column(String, nullable=True)

    links = relationship("DownloadLink", back_populates="metadata_rel")

class ScrapedURL(Base):
    __tablename__ = "scraped_urls"

    url = Column(String, primary_key=True)
    source_name = Column(String, index=True)
    last_scraped = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    status = Column(String, default="success") # 'success' or 'failed'
    scrape_once = Column(Boolean, default=False)
    duration_ms = Column(Integer, nullable=True)
class DownloadHistory(Base):
    __tablename__ = "download_history"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    filename = Column(String)
    category = Column(String) # movie/series
    year = Column(Integer, nullable=True)
    season = Column(String, nullable=True)
    episode = Column(String, nullable=True)
    resolution = Column(String, nullable=True)
    quality = Column(String, nullable=True)
    language = Column(String, nullable=True)
    v_quality = Column(String, nullable=True)
    codec = Column(String, nullable=True)
    network = Column(String, nullable=True)
    audio = Column(String, nullable=True)
    channels = Column(String, nullable=True)
    download_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_auto = Column(Boolean, default=False)
    
    # Reference to centralized metadata for poster/plot in RSS
    imdb_id = Column(String, ForeignKey("media_metadata.imdb_id"), nullable=True)
    metadata_rel = relationship("MediaMetadata")
