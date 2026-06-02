import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.db.models import DownloadHistory, MediaMetadata, DownloadLink
from app.services.maintenance_service import maintenance_service

@pytest.mark.asyncio
async def test_repair_download_history():
    """Test that repair_download_history correctly enriches missing imdb_ids and deletes duplicate entries."""
    
    # Mock entries in history
    # 1. Inside Out 2 (English, no year, no imdb_id)
    h1 = DownloadHistory(
        id=1,
        title="Inside Out 2",
        filename="Inside.Out.2.2024.FRENCH.1080p.mkv",
        category="movie",
        year=None,
        imdb_id=None,
        download_date=None
    )
    # 2. Vice-Versa 2 (French, with year, with imdb_id)
    h2 = DownloadHistory(
        id=2,
        title="Vice-Versa 2",
        filename="Vice-Versa.2.2024.FRENCH.1080p.mkv",
        category="movie",
        year=2024,
        imdb_id="tt21868352",
        download_date=None
    )
    # 3. Inside Out 2 (duplicate of h1/h2, but also no imdb_id)
    h3 = DownloadHistory(
        id=3,
        title="Inside Out 2",
        filename="Inside.Out.2.2024.FRENCH.1080p.mkv",
        category="movie",
        year=None,
        imdb_id=None,
        download_date=None
    )

    # MediaMetadata in DB
    m1 = MediaMetadata(
        imdb_id="tt21868352",
        official_title="Inside Out 2",
        title_fr="Vice-Versa 2",
        year=2024
    )

    with patch("app.services.maintenance_service.AsyncSessionLocal") as mock_db:
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_session
        
        # Mock database select results
        mock_res_history = MagicMock()
        mock_res_history.scalars.return_value.all.return_value = [h1, h2, h3]
        
        mock_res_meta = MagicMock()
        mock_res_meta.scalars.return_value.all.return_value = [m1]
        
        mock_session.execute.side_effect = [
            mock_res_history,  # First select(DownloadHistory)
            mock_res_meta,     # select(MediaMetadata)
            mock_res_history,  # Second select(DownloadHistory) ordered by desc
            MagicMock()        # delete statement execution
        ]
        
        enriched, deleted = await maintenance_service.repair_download_history()
        
        # Verify enrichment worked on h1 and h3
        assert h1.imdb_id == "tt21868352"
        assert h1.title == "Vice-Versa 2"
        assert h1.year == 2024
        
        assert h3.imdb_id == "tt21868352"
        assert h3.title == "Vice-Versa 2"
        assert h3.year == 2024
        
        # Enriched count should be 2 (h1 and h3)
        assert enriched == 2
        
        # Verify deduplication triggered
        # Since h1, h2, and h3 all now have the same key ("tt21868352", "", ""),
        # we should keep one and delete the other two.
        # So deleted count should be 2.
        assert deleted == 2
        print("[TEST] repair_download_history verified successfully!")


@pytest.mark.asyncio
async def test_run_download_task_debrid_error_handling():
    """Test that run_download_task correctly handles string and dict error responses from the debrid service."""
    from app.api.downloads import run_download_task
    
    # Mock debrid client unlock_link
    mock_res_dict_error = {
        "status": "error",
        "error": {
            "code": "LINK_DOWN",
            "message": "This link is not available on the file hoster website"
        }
    }
    
    with patch("app.api.downloads.debrid_service.unlock_link", new_callable=AsyncMock) as mock_unlock, \
         patch("app.api.downloads.AsyncSessionLocal") as mock_db:
        
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_session
        
        mock_unlock.return_value = mock_res_dict_error
        
        # This shouldn't raise AttributeError: 'dict' object has no attribute 'strip'
        await run_download_task(["https://example.com/file.rar"])
        
        # Verify it attempted to unlock
        mock_unlock.assert_called_once_with("https://example.com/file.rar")


@pytest.mark.asyncio
async def test_si_j_en_avais_la_force_duplicate_prevention():
    """Test that a 1080p version auto-download is skipped if a 2160p version exists, even with mismatched imdb_id presence."""
    from app.api.downloads import run_download_task
    
    url = "https://example.com/sijenavaislaforce-1080p"
    
    # Setup the new scraped link (1080p)
    mock_row = MagicMock()
    mock_row.url = url
    mock_row.category = "movie"
    mock_row.title_fr = "Si j'en avais la force"
    mock_row.official_title = "Si j'en avais la force"
    mock_row.title = "Si J_En Avais La Force"
    mock_row.filename = "Si J_En Avais La Force (2025) Multi.Vff.1080P.Web.Eac3.H.265-ParadiZe"
    mock_row.year = 2025
    mock_row.year_1 = 2025
    mock_row.imdb_id = "tt_sijenavaislaforce"
    mock_row.season = None
    mock_row.episode = None
    mock_row.resolution = "1080p"
    mock_row.quality = "WEB"
    mock_row.language = "FRENCH"
    mock_row.v_quality = ""
    mock_row.codec = "H265"
    mock_row.network = ""
    mock_row.audio = "EAC3"
    mock_row.channels = ""
    mock_row.size = None
    mock_row.size_bytes = None
    
    # Setup history entry (2160p, but without imdb_id)
    existing_history = MagicMock(spec=DownloadHistory)
    existing_history.title = "Si.J.En.Avais.La.Force.2025.MULTi.VFF.2160p.DV.HDR.WEB.EAC3.5.1.H265-TFA"
    existing_history.year = 2025
    existing_history.category = "movie"
    existing_history.imdb_id = None  # Crucial mismatch: no imdb_id in history
    existing_history.resolution = "2160p"
    existing_history.quality = "WEB"
    existing_history.language = "FRENCH"
    existing_history.v_quality = "DV HDR"
    existing_history.audio = "EAC3"
    existing_history.codec = "H265"

    with patch("app.api.downloads.debrid_service.unlock_link", new_callable=AsyncMock) as mock_unlock, \
         patch("app.api.downloads.AsyncSessionLocal") as mock_db, \
         patch("app.services.downloader.downloader_service.download_file", new_callable=AsyncMock) as mock_download:
        
        mock_unlock.return_value = {
            "status": "success",
            "data": {
                "link": "https://debrid.com/unlocked",
                "filename": "Si J_En Avais La Force (2025) Multi.Vff.1080P.Web.Eac3.H.265-ParadiZe"
            }
        }
        
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_session
        
        mock_res_meta = MagicMock()
        mock_res_meta.__iter__.return_value = [mock_row]
        
        mock_res_hist = MagicMock()
        mock_res_hist.scalars.return_value.all.return_value = [existing_history]
        
        # We need to trace what session.execute is called with
        async def mock_execute(stmt):
            if "download_history" in str(stmt):
                return mock_res_hist
            return mock_res_meta
        
        mock_session.execute.side_effect = mock_execute
        
        await run_download_task([url], is_auto=True)
        
        # The download should be skipped because we already have a better version (2160p > 1080p)
        mock_download.assert_not_called()
        print("[TEST] 1080p skipped because of existing 2160p verified successfully!")


@pytest.mark.asyncio
async def test_run_download_task_size_filtering():
    """Test that auto-download skips links exceeding AUTO_DOWNLOAD_LOWER_THAN limit."""
    from app.api.downloads import run_download_task
    from app.core.config import settings
    
    url_too_large = "https://example.com/movie-large"
    url_small_enough = "https://example.com/movie-small"
    
    # 25 GB link (exceeds 20GB limit)
    mock_row_large = MagicMock()
    mock_row_large.url = url_too_large
    mock_row_large.category = "movie"
    mock_row_large.official_title = None
    mock_row_large.title_fr = None
    mock_row_large.title = "Large Movie"
    mock_row_large.filename = "Large.Movie.2025.mkv"
    mock_row_large.year = 2025
    mock_row_large.year_1 = 2025
    mock_row_large.size_bytes = 25 * 1024 * 1024 * 1024 # 25 GB
    mock_row_large.size = "25 GB"
    mock_row_large.imdb_id = None
    mock_row_large.season = None
    mock_row_large.episode = None
    mock_row_large.resolution = "1080p"
    mock_row_large.quality = "WEB"
    mock_row_large.language = "FRENCH"
    mock_row_large.v_quality = ""
    mock_row_large.codec = "H265"
    mock_row_large.network = ""
    mock_row_large.audio = "EAC3"
    mock_row_large.channels = ""
    
    # 15 GB link (under 20GB limit)
    mock_row_small = MagicMock()
    mock_row_small.url = url_small_enough
    mock_row_small.category = "movie"
    mock_row_small.official_title = None
    mock_row_small.title_fr = None
    mock_row_small.title = "Small Movie"
    mock_row_small.filename = "Small.Movie.2025.mkv"
    mock_row_small.year = 2025
    mock_row_small.year_1 = 2025
    mock_row_small.size_bytes = 15 * 1024 * 1024 * 1024 # 15 GB
    mock_row_small.size = "15 GB"
    mock_row_small.imdb_id = None
    mock_row_small.season = None
    mock_row_small.episode = None
    mock_row_small.resolution = "1080p"
    mock_row_small.quality = "WEB"
    mock_row_small.language = "FRENCH"
    mock_row_small.v_quality = ""
    mock_row_small.codec = "H265"
    mock_row_small.network = ""
    mock_row_small.audio = "EAC3"
    mock_row_small.channels = ""

    with patch.object(settings, "AUTO_DOWNLOAD_LOWER_THAN", "20GB"), \
         patch("app.api.downloads.AsyncSessionLocal") as mock_db, \
         patch("app.api.downloads.debrid_service.unlock_link", new_callable=AsyncMock) as mock_unlock, \
         patch("app.services.downloader.downloader_service.download_file", new_callable=AsyncMock) as mock_download:
        
        mock_unlock.return_value = {
            "status": "success",
            "data": {
                "link": "https://debrid.com/unlocked",
                "filename": "Small.Movie.2025.mkv"
            }
        }
        
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_session
        
        # Large movie execution
        mock_res_meta_large = MagicMock()
        mock_res_meta_large.__iter__.return_value = [mock_row_large]
        mock_res_hist_large = MagicMock()
        mock_res_hist_large.scalars.return_value.all.return_value = []
        
        async def mock_execute_large(stmt):
            if "download_history" in str(stmt):
                return mock_res_hist_large
            return mock_res_meta_large
        mock_session.execute.side_effect = mock_execute_large
        
        await run_download_task([url_too_large], is_auto=True)
        # Should be skipped!
        mock_download.assert_not_called()
        
        # Reset mock
        mock_download.reset_mock()
        
        # Small movie execution
        mock_res_meta_small = MagicMock()
        mock_res_meta_small.__iter__.return_value = [mock_row_small]
        mock_res_hist_small = MagicMock()
        mock_res_hist_small.scalars.return_value.all.return_value = []
        
        async def mock_execute_small(stmt):
            if "download_history" in str(stmt):
                return mock_res_hist_small
            return mock_res_meta_small
        mock_session.execute.side_effect = mock_execute_small
        
        await run_download_task([url_small_enough], is_auto=True)
        # Should NOT be skipped!
        mock_download.assert_called_once()
        
        print("[TEST] Size filtering auto-download checks verified successfully!")
