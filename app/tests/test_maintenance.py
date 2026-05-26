import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.db.models import DownloadHistory, MediaMetadata
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
