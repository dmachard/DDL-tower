import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.scheduler import run_scraper
from app.db.models import DownloadLink, ScrapedURL
from sqlalchemy import select

@pytest.mark.asyncio
async def test_scheduler_auto_download_trigger():
    """Test that auto_download flag in batch triggers the download task."""
    scraper = MagicMock()
    scraper.name = "TestAutoDL"
    
    # Mock the scraper.run() to yield one batch with auto_download=True
    async def mock_run():
        yield {
            "links": ["https://hoster.com/file1"],
            "source_url": "https://source.com/page1",
            "auto_download": True,
            "override_title": "Test Movie"
        }
    scraper.run = mock_run
    
    # We need to mock several things to isolate the scheduler
    with patch("app.core.scheduler.get_db_ctx") as mock_db_ctx, \
         patch("app.core.scheduler.LinkManager.check_links", new_callable=AsyncMock) as mock_check, \
         patch("app.services.enrichment_service.EnrichmentService.enrich_links", new_callable=AsyncMock) as mock_enrich, \
         patch("app.api.downloads.run_download_task", new_callable=AsyncMock) as mock_dl_task:
        
        # Mock database session
        mock_session = AsyncMock()
        mock_db_ctx.return_value.__aenter__.return_value = mock_session
        
        # Simulate that check_links returns one added link
        mock_link = MagicMock(spec=DownloadLink)
        mock_link.id = 123
        mock_link.url = "https://hoster.com/file1" # Important for the assert later
        mock_check.return_value = [mock_link]
        
        # Mock the result of the DB query inside run_scraper (SELECT * FROM download_links WHERE id IN ...)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_link]
        mock_session.execute.return_value = mock_result
        
        # Run the scheduler logic for this scraper
        await run_scraper(scraper)
        
        # Verify that auto-download was triggered
        mock_dl_task.assert_called_once_with(["https://hoster.com/file1"], is_auto=True)
        print("[TEST] Auto-download trigger verified.")

@pytest.mark.asyncio
async def test_scheduler_duplicate_prevention():
    """Test that already known links are not re-processed for enrichment/download."""
    scraper = MagicMock()
    scraper.name = "TestDup"
    
    async def mock_run():
        yield {
            "links": ["https://hoster.com/old_link"],
            "source_url": "https://source.com/page1",
            "auto_download": True
        }
    scraper.run = mock_run
    
    with patch("app.core.scheduler.get_db_ctx") as mock_db_ctx, \
         patch("app.core.scheduler.LinkManager.check_links", new_callable=AsyncMock) as mock_check, \
         patch("app.api.downloads.run_download_task", new_callable=AsyncMock) as mock_dl_task:
        
        # Mock database session
        mock_session = AsyncMock()
        mock_db_ctx.return_value.__aenter__.return_value = mock_session
        
        # Simulate that check_links returns EMPTY list (link already exists)
        mock_check.return_value = []
        
        await run_scraper(scraper)
        
        # Verify that download task was NOT called
        mock_dl_task.assert_not_called()
        print("[TEST] Duplicate prevention verified (no re-download).")

@pytest.mark.asyncio
async def test_scheduler_auto_download_year_matched():
    """Test that when year filter is set on the step, and the resolved movie matches the year, the download is triggered."""
    scraper = MagicMock()
    scraper.name = "TestAutoDLYearMatch"
    
    async def mock_run():
        yield {
            "links": ["https://hoster.com/file1"],
            "source_url": "https://source.com/page1",
            "auto_download": True,
            "auto_download_years": [2025, 2026],
            "override_title": "Test Movie"
        }
    scraper.run = mock_run
    
    with patch("app.core.scheduler.get_db_ctx") as mock_db_ctx, \
         patch("app.core.scheduler.LinkManager.check_links", new_callable=AsyncMock) as mock_check, \
         patch("app.services.enrichment_service.EnrichmentService.enrich_links", new_callable=AsyncMock) as mock_enrich, \
         patch("app.api.downloads.run_download_task", new_callable=AsyncMock) as mock_dl_task:
        
        mock_session = AsyncMock()
        mock_db_ctx.return_value.__aenter__.return_value = mock_session
        
        mock_link = MagicMock(spec=DownloadLink)
        mock_link.id = 123
        mock_link.url = "https://hoster.com/file1"
        mock_link.year = 2025  # Matches 2025!
        mock_check.return_value = [mock_link]
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_link]
        mock_session.execute.return_value = mock_result
        
        await run_scraper(scraper)
        
        mock_dl_task.assert_called_once_with(["https://hoster.com/file1"], is_auto=True)
        print("[TEST] Year-matched auto-download verified.")

@pytest.mark.asyncio
async def test_scheduler_auto_download_year_unmatched():
    """Test that when year filter is set on the step, but the resolved movie does not match the year, the download is NOT triggered."""
    scraper = MagicMock()
    scraper.name = "TestAutoDLYearUnmatched"
    
    async def mock_run():
        yield {
            "links": ["https://hoster.com/file2"],
            "source_url": "https://source.com/page2",
            "auto_download": True,
            "auto_download_years": [2025, 2026],
            "override_title": "Test Movie 2024"
        }
    scraper.run = mock_run
    
    with patch("app.core.scheduler.get_db_ctx") as mock_db_ctx, \
         patch("app.core.scheduler.LinkManager.check_links", new_callable=AsyncMock) as mock_check, \
         patch("app.services.enrichment_service.EnrichmentService.enrich_links", new_callable=AsyncMock) as mock_enrich, \
         patch("app.api.downloads.run_download_task", new_callable=AsyncMock) as mock_dl_task:
        
        mock_session = AsyncMock()
        mock_db_ctx.return_value.__aenter__.return_value = mock_session
        
        mock_link = MagicMock(spec=DownloadLink)
        mock_link.id = 124
        mock_link.url = "https://hoster.com/file2"
        mock_link.year = 2024  # Does NOT match [2025, 2026]!
        mock_check.return_value = [mock_link]
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_link]
        mock_session.execute.return_value = mock_result
        
        await run_scraper(scraper)
        
        mock_dl_task.assert_not_called()
        print("[TEST] Year-unmatched auto-download skipping verified.")

@pytest.mark.asyncio
async def test_download_duplicate_prevention_accent_insensitive():
    """Test that run_download_task skips auto-download if the movie (even with different accent/case) is already in history."""
    from app.api.downloads import run_download_task
    from app.db.models import DownloadHistory
    
    url = "https://hoster.com/file_chasse"
    
    mock_row = MagicMock()
    mock_row.url = url
    mock_row.category = "movie"
    mock_row.title_fr = "Gardee 2"
    mock_row.official_title = "Gardee 2"
    mock_row.title = "Gardee 2"
    mock_row.filename = "Gardee.2.2025.FRENCH.1080p.WEB.H264.mkv"
    mock_row.year = 2025
    mock_row.year_1 = 2025
    mock_row.imdb_id = None
    mock_row.season = None
    mock_row.episode = None
    mock_row.resolution = "1080p"
    mock_row.quality = "WEB"
    mock_row.language = "FRENCH"
    mock_row.v_quality = ""
    mock_row.codec = "H264"
    mock_row.network = ""
    mock_row.audio = ""
    mock_row.channels = ""

    existing_history = MagicMock(spec=DownloadHistory)
    existing_history.title = "gardée 2"
    existing_history.year = 2025
    existing_history.category = "movie"
    existing_history.resolution = "1080p"
    existing_history.quality = "WEB"
    existing_history.language = "VFF"
    existing_history.v_quality = ""
    existing_history.audio = ""

    with patch("app.api.downloads.debrid_service.unlock_link", new_callable=AsyncMock) as mock_unlock, \
         patch("app.api.downloads.AsyncSessionLocal") as mock_db, \
         patch("app.services.downloader.downloader_service.download_file", new_callable=AsyncMock) as mock_download:
        
        mock_unlock.return_value = {
            "status": "success",
            "data": {
                "link": "https://debrid.com/unlocked",
                "filename": "Gardee.2.2025.FRENCH.1080p.WEB.H264.mkv"
            }
        }
        
        mock_session = AsyncMock()
        mock_db.return_value.__aenter__.return_value = mock_session
        
        mock_res_meta = MagicMock()
        mock_res_meta.__iter__.return_value = [mock_row]
        
        mock_res_hist = MagicMock()
        mock_res_hist.scalars.return_value.all.return_value = [existing_history]
        
        mock_session.execute.side_effect = [mock_res_meta, mock_res_hist]
        
        await run_download_task([url], is_auto=True)
        
        mock_download.assert_not_called()
        print("[TEST] Accent-insensitive duplicate prevention verified successfully!")
