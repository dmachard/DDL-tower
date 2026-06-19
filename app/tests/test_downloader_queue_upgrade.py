import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from app.db.models import ActiveDownload
from app.services.downloader import DownloaderService

@pytest.mark.asyncio
async def test_downloader_skips_lower_quality_when_better_queued():
    """
    Test that a lower-quality download (e.g., H264) is skipped when a
    higher-quality download (e.g., H265) for the same content is waiting in the queue.
    """
    service = DownloaderService()
    
    # Pre-register both files in memory
    service.pre_register_files([
        ("http://example.com/movie.h264.mkv", "movie.h264.mkv"),
        ("http://example.com/movie.h265.mkv", "movie.h265.mkv")
    ])
    
    # Mock row representing the better version (H265) which is waiting in the queue
    better_row = MagicMock(spec=ActiveDownload)
    better_row.url = "http://example.com/movie.h265.mkv"
    better_row.filename = "movie.h265.mkv"
    better_row.category = "movie"
    better_row.title = "Test Movie"
    better_row.year = 2026
    better_row.imdb_id = "tt1234567"
    better_row.status = "waiting"
    better_row.resolution = "1080p"
    better_row.quality = "WEB"
    better_row.language = "FRENCH"
    better_row.v_quality = ""
    better_row.codec = "H265"  # Better codec score (+5)
    better_row.audio = ""
    better_row.channels = ""
    
    current_row = MagicMock(spec=ActiveDownload)
    current_row.url = "http://example.com/movie.h264.mkv"
    
    mock_session = AsyncMock()
    
    # Define response mocks once to preserve object identity
    mock_res_active = MagicMock()
    mock_res_active.scalars.return_value.all.return_value = [better_row]
    
    mock_res_delete = MagicMock()
    mock_res_delete.scalar_one_or_none.return_value = current_row
    mock_res_delete.scalars.return_value.first.return_value = current_row
    
    async def mock_execute(query, *args, **kwargs):
        query_str = str(query)
        url_param = None
        try:
            for k, v in query.compile().params.items():
                if "url" in k:
                    url_param = v
        except Exception:
            pass
            
        if "active_downloads.url =" in query_str:
            if url_param == "http://example.com/movie.h264.mkv":
                return mock_res_delete
            else:
                mock_empty = MagicMock()
                mock_empty.scalar_one_or_none.return_value = None
                mock_empty.scalars.return_value.first.return_value = None
                return mock_empty
        return mock_res_active
        
    mock_session.execute.side_effect = mock_execute
    
    # Setup mock ClientSession
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.headers = {"Content-Length": "1000"}
    
    mock_head_ctx = MagicMock()
    mock_head_ctx.__aenter__.return_value = mock_resp
    
    mock_client_session_inst = MagicMock()
    mock_client_session_inst.head.return_value = mock_head_ctx
    
    mock_client_session = MagicMock()
    mock_client_session.return_value.__aenter__.return_value = mock_client_session_inst
    
    with patch("app.db.database.AsyncSessionLocal") as mock_db, \
         patch("app.services.library_service.library_service.find_in_library", return_value=None), \
         patch("pathlib.Path.exists", return_value=False), \
         patch("aiohttp.ClientSession", mock_client_session):
         
        mock_db.return_value.__aenter__.return_value = mock_session
        
        # Trigger download of the lower-quality version (H264)
        result = await service._do_download(
            url="http://example.com/movie.h264.mkv",
            filename="movie.h264.mkv",
            category="movie",
            title="Test Movie",
            year=2026,
            imdb_id="tt1234567",
            resolution="1080p",
            quality="WEB",
            language="FRENCH",
            v_quality="",
            codec="H264"  # Lower quality codec score
        )
        
        # Lower quality download should be skipped (returns None)
        assert result is None
        
        # Group should be removed from active downloads list
        assert "movie.h264.mkv" not in service.active_downloads
        
        # The database row for the skipped version should be deleted
        mock_session.delete.assert_called_once_with(current_row)
        print("[TEST] Upgrade-queue skip test passed successfully!")

@pytest.mark.asyncio
async def test_downloader_cancels_active_download_when_better_added():
    """
    Test that when a lower-quality download is already actively downloading,
    adding a higher-quality version immediately cancels the active lower-quality one
    and deletes its partial file.
    """
    service = DownloaderService()
    
    # Setup mock active download for the lower-quality version (H264)
    low_row = MagicMock(spec=ActiveDownload)
    low_row.url = "http://example.com/movie.h264.mkv"
    low_row.filename = "movie.h264.mkv"
    low_row.category = "movie"
    low_row.title = "Test Movie"
    low_row.year = 2026
    low_row.imdb_id = "tt1234567"
    low_row.status = "downloading"
    low_row.resolution = "1080p"
    low_row.quality = "WEB"
    low_row.language = "FRENCH"
    low_row.v_quality = ""
    low_row.codec = "H264"
    low_row.audio = ""
    low_row.channels = ""
    
    mock_session = AsyncMock()
    
    # Define response mocks once to preserve object identity
    mock_res_active_1 = MagicMock()
    mock_res_active_1.scalars.return_value.all.return_value = []
    
    mock_res_active_2 = MagicMock()
    mock_res_active_2.scalars.return_value.all.return_value = [low_row]
    
    mock_res_delete = MagicMock()
    mock_res_delete.scalar_one_or_none.return_value = low_row
    mock_res_delete.scalars.return_value.first.return_value = low_row
    
    async def mock_execute(query, *args, **kwargs):
        query_str = str(query)
        url_param = None
        try:
            for k, v in query.compile().params.items():
                if "url" in k:
                    url_param = v
        except Exception:
            pass
            
        if "active_downloads.url =" in query_str:
            if url_param == "http://example.com/movie.h264.mkv":
                return mock_res_delete
            else:
                mock_empty = MagicMock()
                mock_empty.scalar_one_or_none.return_value = None
                mock_empty.scalars.return_value.first.return_value = None
                return mock_empty
        elif "active_downloads.url <>" in query_str or "active_downloads.url !=" in query_str:
            return mock_res_active_2
        return mock_res_active_1
        
    mock_session.execute.side_effect = mock_execute
    
    service.pre_register_files([
        ("http://example.com/movie.h264.mkv", "movie.h264.mkv"),
        ("http://example.com/movie.h265.mkv", "movie.h265.mkv")
    ])
    
    # Setup mock ClientSession
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.headers = {"Content-Length": "1000"}
    
    async def mock_iter_chunks(size):
        yield b"chunk1"
        await asyncio.sleep(0.2)
        yield b"chunk2"
        
    mock_resp.content.iter_chunked = mock_iter_chunks
    
    mock_get_ctx = MagicMock()
    mock_get_ctx.__aenter__.return_value = mock_resp
    
    mock_head_ctx = MagicMock()
    mock_head_ctx.__aenter__.return_value = mock_resp
    
    mock_client_session_inst = MagicMock()
    mock_client_session_inst.get.return_value = mock_get_ctx
    mock_client_session_inst.head.return_value = mock_head_ctx
    
    mock_client_session = MagicMock()
    mock_client_session.return_value.__aenter__.return_value = mock_client_session_inst
    
    file_exists = True
    def mock_exists():
        return file_exists
    
    mock_unlink_called = False
    def mock_unlink():
        nonlocal mock_unlink_called
        mock_unlink_called = True
        
    mock_stat = MagicMock()
    mock_stat.st_size = 0
    
    with patch("app.db.database.AsyncSessionLocal") as mock_db, \
         patch("app.services.library_service.library_service.find_in_library", return_value=None), \
         patch("pathlib.Path.exists", side_effect=mock_exists), \
         patch("pathlib.Path.stat", return_value=mock_stat), \
         patch("pathlib.Path.unlink", side_effect=mock_unlink), \
         patch("aiohttp.ClientSession", mock_client_session), \
         patch("builtins.open", MagicMock()):
         
        mock_db.return_value.__aenter__.return_value = mock_session
        
        # Start H264 download in background using download_file to acquire the lock
        h264_task = asyncio.create_task(service.download_file(
            url="http://example.com/movie.h264.mkv",
            filename="movie.h264.mkv",
            category="movie",
            title="Test Movie",
            year=2026,
            imdb_id="tt1234567",
            resolution="1080p",
            quality="WEB",
            language="FRENCH",
            v_quality="",
            codec="H264"
        ))
        
        # Let H264 start and enter chunk loop (acquiring lock)
        await asyncio.sleep(0.05)
        
        # Trigger download of H265 (which checks and cancels H264)
        h265_task = asyncio.create_task(service.download_file(
            url="http://example.com/movie.h265.mkv",
            filename="movie.h265.mkv",
            category="movie",
            title="Test Movie",
            year=2026,
            imdb_id="tt1234567",
            resolution="1080p",
            quality="WEB",
            language="FRENCH",
            v_quality="",
            codec="H265"
        ))
        
        # Await H264 task completion (should return None due to cancellation)
        h264_result = await h264_task
        assert h264_result is None
        
        # Verify unlinked
        assert mock_unlink_called is True
        
        # Verify deleted in DB
        mock_session.delete.assert_called_once_with(low_row)
        
        # Cleanup pending H265 task (it's holding the lock/downloading, we cancel it)
        h265_task.cancel()
        try:
            await h265_task
        except asyncio.CancelledError:
            pass
        print("[TEST] Dynamic cancellation test passed successfully!")
