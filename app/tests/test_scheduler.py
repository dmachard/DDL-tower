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
async def test_scheduler_auto_download_resolution_matched():
    """Test that when resolution filter is set, and the resolved movie matches the resolution, the download is triggered."""
    scraper = MagicMock()
    scraper.name = "TestAutoDLResMatch"
    
    async def mock_run():
        yield {
            "links": ["https://hoster.com/file1"],
            "source_url": "https://source.com/page1",
            "auto_download": True,
            "auto_download_resolutions": ["1080p", "4kLight"],
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
        mock_link.resolution = "1080p"  # Matches 1080p!
        mock_check.return_value = [mock_link]
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_link]
        mock_session.execute.return_value = mock_result
        
        await run_scraper(scraper)
        
        mock_dl_task.assert_called_once_with(["https://hoster.com/file1"], is_auto=True)
        print("[TEST] Resolution-matched auto-download verified.")


@pytest.mark.asyncio
async def test_scheduler_auto_download_resolution_unmatched():
    """Test that when resolution filter is set, but the resolved movie does not match the resolution, download is skipped."""
    scraper = MagicMock()
    scraper.name = "TestAutoDLResUnmatched"
    
    async def mock_run():
        yield {
            "links": ["https://hoster.com/file2"],
            "source_url": "https://source.com/page2",
            "auto_download": True,
            "auto_download_resolutions": ["1080p", "4kLight"],
            "override_title": "Test Movie 720p"
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
        mock_link.resolution = "720p"  # Does NOT match!
        mock_check.return_value = [mock_link]
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_link]
        mock_session.execute.return_value = mock_result
        
        await run_scraper(scraper)
        
        mock_dl_task.assert_not_called()
        print("[TEST] Resolution-unmatched auto-download skipping verified.")

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

@pytest.mark.asyncio
async def test_scheduler_enable_flag():
    """Test that disabled scrapers are skipped in full runs but manual/targeted runs bypass this check."""
    from app.core.scheduler import run_scrapers
    
    scraper_enabled = MagicMock()
    scraper_enabled.name = "EnabledScraper"
    scraper_enabled.enabled = True
    
    scraper_disabled = MagicMock()
    scraper_disabled.name = "DisabledScraper"
    scraper_disabled.enabled = False
    
    with patch("app.core.scheduler.get_scrapers", new_callable=AsyncMock) as mock_get_scrapers, \
         patch("app.core.scheduler.run_scraper", new_callable=AsyncMock) as mock_run_scraper, \
         patch("app.core.scheduler.enrichment_service.enrich_links", new_callable=AsyncMock):
        
        mock_get_scrapers.return_value = [scraper_enabled, scraper_disabled]
        
        # Scenario 1: Full run (no specific source)
        await run_scrapers(source_name=None)
        
        # Enabled should be run, disabled should be skipped
        mock_run_scraper.assert_any_call(scraper_enabled)
        # Verify disabled was not called
        assert scraper_disabled not in [call.args[0] for call in mock_run_scraper.call_args_list]
        
        # Reset the mock calls
        mock_run_scraper.reset_mock()
        
        # Scenario 2: Manual specific source run for the disabled scraper
        await run_scrapers(source_name="DisabledScraper")
        
        # The disabled scraper should be executed because it was targeted specifically
        mock_run_scraper.assert_called_once_with(scraper_disabled)
        print("[TEST] Scraper enable/disable scheduling and manual override verified.")

@pytest.mark.asyncio
async def test_scheduler_loop_schedule_hour():
    """Test scheduler_loop behavior with per-source schedule_hour."""
    from app.core.scheduler import scheduler_loop
    
    scraper_scheduled = MagicMock()
    scraper_scheduled.name = "ScheduledScraper"
    scraper_scheduled.enabled = True
    scraper_scheduled.config = {"schedule_hour": 1}
    
    scraper_interval = MagicMock()
    scraper_interval.name = "IntervalScraper"
    scraper_interval.enabled = True
    scraper_interval.config = {}
    
    # Mock datetime to control current hour
    mock_now = MagicMock()
    # Let's say current hour is 1 (matching scheduled scraper)
    mock_now.hour = 1
    mock_now.strftime.return_value = "2026-05-29"
    
    with patch("app.core.scheduler.get_scrapers", new_callable=AsyncMock) as mock_get_scrapers, \
         patch("app.core.scheduler.run_scraper", new_callable=AsyncMock) as mock_run_scraper, \
         patch("app.core.scheduler.is_in_scan_window", return_value=False), \
         patch("app.core.scheduler.enrichment_service.enrich_links", new_callable=AsyncMock) as mock_enrich, \
         patch("datetime.datetime") as mock_datetime, \
         patch("asyncio.sleep", side_effect=Exception("Exit Loop")):
         
        mock_datetime.now.return_value = mock_now
        mock_get_scrapers.return_value = [scraper_scheduled, scraper_interval]
        
        with pytest.raises(Exception, match="Exit Loop"):
            await scheduler_loop()
            
        # Scheduled scraper should be run because hour matches 1
        mock_run_scraper.assert_any_call(scraper_scheduled)
        
        # Interval scraper should NOT be run because is_in_scan_window is False and it's an interval scraper
        run_args = [call.args[0] for call in mock_run_scraper.call_args_list]
        assert scraper_scheduled in run_args
        assert scraper_interval not in run_args
        
        # Verify enrichment was triggered because run_any was True
        mock_enrich.assert_called_once()
        print("[TEST] Per-source schedule_hour execution logic verified successfully!")

@pytest.mark.asyncio
async def test_post_scraping_flow_auto_export():
    """Test that post_scraping_flow calls ExportCommands.run_export if AUTO_EXPORT_ENABLED is True."""
    from app.core.scheduler import post_scraping_flow
    
    with patch("app.core.scheduler.settings") as mock_settings, \
         patch("app.core.scheduler.enrichment_service.enrich_links", new_callable=AsyncMock) as mock_enrich, \
         patch("app.cli.export.ExportCommands.run_export", new_callable=AsyncMock) as mock_export:
         
        # Case 1: Disabled
        mock_settings.AUTO_EXPORT_ENABLED = False
        mock_settings.AUTO_EXPORT_TYPE = "stats"
        await post_scraping_flow()
        mock_enrich.assert_called_once()
        mock_export.assert_not_called()
        
        # Case 2: Enabled
        mock_enrich.reset_mock()
        mock_settings.AUTO_EXPORT_ENABLED = True
        await post_scraping_flow()
        mock_enrich.assert_called_once()
        mock_export.assert_called_once_with(export_type="stats")

