import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.extraction import ExtractionService
from app.services.downloader import DownloaderService

def test_check_missing_parts(tmp_path):
    # Setup temporary files representing download parts
    # No files
    svc = ExtractionService(download_dir=str(tmp_path))
    assert svc.check_missing_parts(str(tmp_path / "Euphoria.part1.rar")) == []

    # Single file (not multipart)
    single_file = tmp_path / "Euphoria.rar"
    single_file.touch()
    assert svc.check_missing_parts(str(single_file)) == []

    # Multipart files with missing part 3
    p1 = tmp_path / "Euphoria.part1.rar"
    p2 = tmp_path / "Euphoria.part2.rar"
    p4 = tmp_path / "Euphoria.part4.rar"
    p1.touch()
    p2.touch()
    p4.touch()
    
    assert svc.check_missing_parts(str(p1)) == [3]

    # All multipart files present
    p3 = tmp_path / "Euphoria.part3.rar"
    p3.touch()
    assert svc.check_missing_parts(str(p1)) == []


def test_should_extract_with_missing_parts(tmp_path):
    svc = ExtractionService(download_dir=str(tmp_path))
    
    # Missing parts
    p1 = tmp_path / "Euphoria.part1.rar"
    p2 = tmp_path / "Euphoria.part2.rar"
    p4 = tmp_path / "Euphoria.part4.rar"
    p1.touch()
    p2.touch()
    p4.touch()

    # Active downloads dict
    active = {
        "euphoria": {
            "files": {
                "Euphoria.part1.rar": {"status": "done", "progress": 100},
                "Euphoria.part2.rar": {"status": "done", "progress": 100},
                "Euphoria.part4.rar": {"status": "done", "progress": 100},
            }
        }
    }
    
    # should_extract returns False since part 3 is missing
    assert svc.should_extract(str(p1), active) is False

    # Once part 3 is created on disk
    p3 = tmp_path / "Euphoria.part3.rar"
    p3.touch()
    assert svc.should_extract(str(p1), active) is True


@pytest.mark.asyncio
async def test_downloader_missing_parts_error(tmp_path):
    downloader = DownloaderService(download_dir=str(tmp_path))
    p1 = tmp_path / "Euphoria.part1.rar"
    p2 = tmp_path / "Euphoria.part2.rar"
    p4 = tmp_path / "Euphoria.part4.rar"
    p1.touch()
    p2.touch()
    p4.touch()

    downloader.pre_register_files([
        ("http://example.com/Euphoria.part1.rar", "Euphoria.part1.rar"),
        ("http://example.com/Euphoria.part2.rar", "Euphoria.part2.rar"),
        ("http://example.com/Euphoria.part4.rar", "Euphoria.part4.rar"),
    ])

    # Mark them as done
    downloader.active_downloads["Euphoria"]["files"]["Euphoria.part1.rar"]["status"] = "done"
    downloader.active_downloads["Euphoria"]["files"]["Euphoria.part1.rar"]["progress"] = 100
    downloader.active_downloads["Euphoria"]["files"]["Euphoria.part2.rar"]["status"] = "done"
    downloader.active_downloads["Euphoria"]["files"]["Euphoria.part2.rar"]["progress"] = 100
    downloader.active_downloads["Euphoria"]["files"]["Euphoria.part4.rar"]["status"] = "done"
    downloader.active_downloads["Euphoria"]["files"]["Euphoria.part4.rar"]["progress"] = 100

    # Call _finalize_download
    with patch("app.core.config.settings.EXTRACT_RAR", True):
        res = await downloader._finalize_download(
            p1, "Euphoria.part1.rar", "Euphoria", "series", "Euphoria", 2026, False
        )
        assert res == str(p1)
        # Check that group status is error with Missing part(s)
        assert downloader.active_downloads["Euphoria"]["status"] == "error"
        assert "Missing part(s): part3" in downloader.active_downloads["Euphoria"]["error"]


@pytest.mark.asyncio
async def test_debrid_service_unlock_retry():
    from app.debrid.debrid import DebridService
    
    mock_client = AsyncMock()
    # First response: temporary hoster error
    # Second response: success
    mock_client.unlock_link.side_effect = [
        {"status": "error", "error": "This link is not available on the file hoster website"},
        {"status": "success", "data": {"link": "http://ok.com/file.mkv", "filename": "file.mkv"}}
    ]
    
    svc = DebridService()
    with patch.object(svc, "get_enabled_clients", return_value=[mock_client]):
        res = await svc.unlock_link("http://some-link.com")
        assert res["status"] == "success"
        assert res["data"]["link"] == "http://ok.com/file.mkv"
        assert mock_client.unlock_link.call_count == 2
