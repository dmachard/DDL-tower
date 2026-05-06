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
