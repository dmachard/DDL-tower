import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.downloader import DownloaderService
from app.db.models import ActiveDownload

@pytest.mark.asyncio
async def test_downloader_pause_group():
    # Instantiate downloader service
    service = DownloaderService()
    
    # Pre-register some files
    service.pre_register_files([("http://example.com/movie.part1.rar", "movie.part1.rar")])
    
    # Check that in-memory state is set up
    assert "movie" in service.active_downloads
    assert service.active_downloads["movie"]["status"] == "waiting"
    
    # Mock database session
    mock_session = AsyncMock()
    mock_row = MagicMock()
    mock_row.filename = "movie.part1.rar"
    mock_row.status = "waiting"
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_row]
    mock_session.execute.return_value = mock_result

    with patch("app.db.database.AsyncSessionLocal") as mock_db:
        mock_db.return_value.__aenter__.return_value = mock_session
        
        # Pause group
        await service.pause_group("movie")
        
        # Check in-memory status
        assert service.active_downloads["movie"]["status"] == "paused"
        assert service.active_downloads["movie"]["files"]["movie.part1.rar"]["status"] == "paused"
        
        # Check database row status was updated
        assert mock_row.status == "paused"


@pytest.mark.asyncio
async def test_downloader_resume_group():
    service = DownloaderService()
    service.pre_register_files([("http://example.com/movie.part1.rar", "movie.part1.rar")])
    
    # Force pause state
    service.active_downloads["movie"]["status"] = "paused"
    service.active_downloads["movie"]["files"]["movie.part1.rar"]["status"] = "paused"
    
    # Mock database row
    mock_row = MagicMock()
    mock_row.url = "http://example.com/movie.part1.rar"
    mock_row.filename = "movie.part1.rar"
    mock_row.status = "paused"
    mock_row.error = "some error"
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_row]
    mock_session.execute.return_value = mock_result

    with patch("app.db.database.AsyncSessionLocal") as mock_db, \
         patch.object(service, "download_file", new_callable=AsyncMock) as mock_download_file:
         
        mock_db.return_value.__aenter__.return_value = mock_session
        
        # Resume group
        await service.resume_group("movie")
        
        # Check that state was reset to waiting
        assert service.active_downloads["movie"]["status"] == "waiting"
        assert service.active_downloads["movie"]["files"]["movie.part1.rar"]["status"] == "waiting"
        
        # Check DB updates
        assert mock_row.status == "waiting"
        assert mock_row.error is None
        
        # Verify background download was triggered
        await asyncio.sleep(0.1) # Yield control to let async task run
        mock_download_file.assert_called_once()


@pytest.mark.asyncio
async def test_downloader_delete_group():
    service = DownloaderService()
    service.pre_register_files([("http://example.com/movie.part1.rar", "movie.part1.rar")])
    
    # Mock database row
    mock_row = MagicMock()
    mock_row.filename = "movie.part1.rar"
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_row]
    mock_session.execute.return_value = mock_result

    with patch("app.db.database.AsyncSessionLocal") as mock_db:
        mock_db.return_value.__aenter__.return_value = mock_session
        
        # Delete group
        await service.delete_group("movie")
        
        # Check that it was removed from memory
        assert "movie" not in service.active_downloads
        
        # Check DB deletion was called
        mock_session.delete.assert_called_once_with(mock_row)


@pytest.mark.asyncio
async def test_downloader_resume_active_downloads_on_startup():
    service = DownloaderService()
    
    # Simulate two active downloads in DB, one paused and one downloading
    row1 = MagicMock()
    row1.url = "http://example.com/movie.part1.rar"
    row1.filename = "movie.part1.rar"
    row1.status = "downloading"
    
    row2 = MagicMock()
    row2.url = "http://example.com/show.s01e01.mkv"
    row2.filename = "show.s01e01.mkv"
    row2.status = "paused"
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [row1, row2]
    mock_session.execute.return_value = mock_result

    with patch("app.db.database.AsyncSessionLocal") as mock_db, \
         patch.object(service, "download_file", new_callable=AsyncMock) as mock_download_file:
         
        mock_db.return_value.__aenter__.return_value = mock_session
        
        # Run startup resume
        await service.resume_active_downloads()
        
        # Verify in-memory structures were reconstructed
        assert "movie" in service.active_downloads
        assert service.active_downloads["movie"]["status"] == "waiting"
        
        assert "show.s01e01.mkv" in service.active_downloads
        assert service.active_downloads["show.s01e01.mkv"]["status"] == "paused"
        
        # Verify that only the non-paused download was resumed
        await asyncio.sleep(0.1) # yield
        mock_download_file.assert_called_once()
        args, kwargs = mock_download_file.call_args
        assert args[0] == "http://example.com/movie.part1.rar"
