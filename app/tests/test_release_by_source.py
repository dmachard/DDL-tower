import time
from unittest.mock import patch
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.db.models import DownloadLink, MediaMetadata, ScrapedURL
from app.services.release_service import ReleaseService


@pytest.mark.asyncio
async def test_by_source_lightweight_and_detail():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    p = patch("app.services.release_service.settings")
    mock_settings = p.start()
    mock_settings.SCRAPER_SOURCES = [{"name": "SrcA", "enabled": True}]
    mock_settings.SCAN_INTERVAL_MINUTES = 60
    mock_settings.SCAN_NOVELTY_MULTIPLIER = 2
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as async_db:
            ReleaseService.invalidate_cache()
            now = datetime.now(timezone.utc)
            old_time = now - timedelta(days=5)

            async_db.add(ScrapedURL(url="https://src1.test/index", source_name="SrcA", last_scraped=now))
            async_db.add_all([
                MediaMetadata(imdb_id="tt0000001", official_title="Test Movie", year=2025, poster_path="tt0000001.jpg"),
                MediaMetadata(imdb_id="tt0000002", official_title="Test Series", year=2024, poster_path="tt0000002.jpg"),
            ])
            async_db.add_all([
                DownloadLink(
                    url="https://1f.test/m1", hoster="1fichier", status="alive",
                    filename="Test.Movie.2025.1080p.mkv", size="4.2 GB", size_bytes=4200000000,
                    last_checked=now, source_name="SrcA", title="Test Movie",
                    category="movie", year=2025, resolution="1080p", imdb_id="tt0000001"
                ),
                DownloadLink(
                    url="https://1f.test/m2", hoster="1fichier", status="alive",
                    filename="Test.Movie.2025.720p.mkv", size="2.1 GB", size_bytes=2100000000,
                    created_at=old_time, last_checked=old_time, source_name="SrcA", title="Test Movie",
                    category="movie", year=2025, resolution="720p", imdb_id="tt0000001"
                ),
                DownloadLink(
                    url="https://1f.test/s1", hoster="1fichier", status="alive",
                    filename="Test.Series.S01E01.1080p.mkv", size="1.5 GB", size_bytes=1500000000,
                    last_checked=now, source_name="SrcA", title="Test Series",
                    category="series", year=2024, season="1", episode="1", resolution="1080p", imdb_id="tt0000002"
                ),
                DownloadLink(
                    url="https://1f.test/dead", hoster="1fichier", status="dead",
                    filename="Dead.Movie.mkv", size="1 GB", size_bytes=1000000000,
                    last_checked=now, source_name="SrcA", title="Dead Movie",
                    category="movie", year=2025, resolution="1080p"
                ),
            ])
            await async_db.commit()

            # 1. All categories: returns lightweight rows without resolutions
            res = await ReleaseService.get_releases_by_source(async_db, recent=False)
            assert len(res["rows"]) == 2
            by_cat = {r["category"]: r for r in res["rows"]}
            assert set(by_cat.keys()) == {"movie", "series"}

            movie_item = by_cat["movie"]["items"][0]
            assert movie_item["resolutions"] is None
            assert movie_item["all_count"] == 2
            assert movie_item["new_count"] == 1
            assert movie_item["poster_path"] == "tt0000001.jpg"

            # 2. Category filter returns only requested category
            movies_only = await ReleaseService.get_releases_by_source(async_db, category="movie", recent=False)
            assert len(movies_only["rows"]) == 1
            assert movies_only["rows"][0]["category"] == "movie"

            # 3. Detail endpoint loads full resolutions + is_new flags + dead links on demand
            async_db.add(DownloadLink(
                url="https://1f.test/m_dead", hoster="1fichier", status="dead",
                filename="Test.Movie.2025.480p.mkv", size="800 MB", size_bytes=800000000,
                created_at=old_time, last_checked=now, source_name="SrcA", title="Test Movie",
                category="movie", year=2025, resolution="480p", imdb_id="tt0000001"
            ))
            await async_db.commit()

            detail = await ReleaseService.get_release_detail(async_db, imdb_id="tt0000001")
            assert set(detail["resolutions"].keys()) == {"1080p", "720p", "480p"}
            assert detail["resolutions"]["1080p"][0]["sub_releases"][0]["is_new"] is True
            assert detail["resolutions"]["720p"][0]["sub_releases"][0]["is_new"] is False
            assert detail["resolutions"]["480p"][0]["sub_releases"][0]["parts"][0]["status"] == "dead"

            # 4. Cache hit + invalidation
            cached = await ReleaseService.get_releases_by_source(async_db, recent=False)
            assert cached is res
            ReleaseService.invalidate_cache()
            refetched = await ReleaseService.get_releases_by_source(async_db, recent=False)
            assert refetched is not res
    finally:
        p.stop()
        await engine.dispose()


@pytest.mark.asyncio
async def test_by_source_performance_large_dataset():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    p = patch("app.services.release_service.settings")
    mock_settings = p.start()
    mock_settings.SCRAPER_SOURCES = [{"name": f"Src{i}", "enabled": True} for i in range(6)]
    mock_settings.SCAN_INTERVAL_MINUTES = 60
    mock_settings.SCAN_NOVELTY_MULTIPLIER = 2
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with Session() as async_db:
            now = datetime.now(timezone.utc)
            async_db.add(ScrapedURL(url="https://perf.test/index", source_name="Src0", last_scraped=now))

            # Bulk insert 20,000 links across 6 sources (movies + multi-episode series)
            metas = [
                MediaMetadata(imdb_id=f"tt{1000000 + i}", official_title=f"Title {i}", year=2025, poster_path=f"tt{1000000 + i}.jpg")
                for i in range(400)
            ]
            async_db.add_all(metas)

            links = []
            for i in range(20000):
                src_idx = i % 6
                is_series = ((i // 6) % 2 == 1)
                title_idx = i % 400
                links.append(DownloadLink(
                    url=f"https://1f.test/perf/{i}",
                    hoster="1fichier",
                    status="alive",
                    filename=f"Title.{title_idx}.{i}.1080p.mkv",
                    size="2 GB",
                    size_bytes=2000000000,
                    last_checked=now - timedelta(seconds=i),
                    source_name=f"Src{src_idx}",
                    title=f"Title {title_idx}",
                    category="series" if is_series else "movie",
                    year=2025,
                    season="1" if is_series else None,
                    episode=str((i % 50) + 1) if is_series else None,
                    resolution="1080p",
                    imdb_id=f"tt{1000000 + title_idx}",
                ))
            async_db.add_all(links)
            await async_db.commit()

            ReleaseService.invalidate_cache()
            t0 = time.perf_counter()
            all_res = await ReleaseService.get_releases_by_source(async_db, recent=False)
            t_all = time.perf_counter() - t0
            assert len(all_res["rows"]) == 12
            assert t_all < 0.5, f"by-source all too slow: {t_all:.3f}s"

            ReleaseService.invalidate_cache()
            t0 = time.perf_counter()
            mov_res = await ReleaseService.get_releases_by_source(async_db, category="movie", recent=False)
            t_mov = time.perf_counter() - t0
            assert len(mov_res["rows"]) == 6
            assert t_mov < 0.5, f"by-source movie too slow: {t_mov:.3f}s"

            ReleaseService.invalidate_cache()
            t0 = time.perf_counter()
            ser_res = await ReleaseService.get_releases_by_source(async_db, category="series", recent=False)
            t_ser = time.perf_counter() - t0
            assert len(ser_res["rows"]) == 6
            assert t_ser < 0.5, f"by-source series too slow: {t_ser:.3f}s"

            t0 = time.perf_counter()
            detail = await ReleaseService.get_release_detail(async_db, imdb_id="tt1000001")
            t_det = time.perf_counter() - t0
            assert detail["count"] > 0
            assert t_det < 0.2, f"detail too slow: {t_det:.3f}s"

            print(f"\n[PERF 20k rows] all={t_all*1000:.1f}ms movie={t_mov*1000:.1f}ms series={t_ser*1000:.1f}ms detail={t_det*1000:.1f}ms")
    finally:
        p.stop()
        await engine.dispose()
