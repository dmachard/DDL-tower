import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from app.api.stats import rescan_error
from app.db.models import ScrapedURL, DownloadLink

@pytest.mark.asyncio
async def test_rescan_error_not_found():
    """Test rescan_error raises 404 when url is not in ScrapedURL."""
    mock_session = AsyncMock()
    mock_scraped_res = MagicMock()
    mock_scraped_res.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_scraped_res

    with pytest.raises(HTTPException) as exc_info:
        await rescan_error(url="https://hoster.com/nonexistent", db=mock_session)

    assert exc_info.value.status_code == 404
    assert "not found" in exc_info.value.detail

@pytest.mark.asyncio
async def test_rescan_error_success():
    """Test rescan_error succeeds when link is checked successfully."""
    mock_session = AsyncMock()

    mock_scraped = MagicMock(spec=ScrapedURL)
    mock_scraped.url = "https://hoster.com/file1"
    mock_scraped.source_name = "Hoster-Check"
    mock_scraped.screenshot_path = "static/error_dumps/screenshot.png"
    mock_scraped.html_path = "static/error_dumps/dump.html"

    mock_dl = MagicMock(spec=DownloadLink)
    mock_dl.url = "https://hoster.com/file1"
    mock_dl.source_name = "Hoster-Check"
    mock_dl.status = "error"

    mock_new_dl = MagicMock(spec=DownloadLink)
    mock_new_dl.url = "https://hoster.com/file1"
    mock_new_dl.status = "alive"

    dl_queries_count = 0
    async def mock_execute(query, *args, **kwargs):
        nonlocal dl_queries_count
        query_str = str(query)
        mock_res = MagicMock()
        if "FROM scraped_urls" in query_str or "scraped_urls" in query_str:
            mock_res.scalar_one_or_none.return_value = mock_scraped
        elif "FROM download_links" in query_str or "download_links" in query_str:
            if "IN (" in query_str:
                mock_res.all.return_value = []
            else:
                dl_queries_count += 1
                if dl_queries_count == 1:
                    mock_res.scalar_one_or_none.return_value = mock_dl
                else:
                    mock_res.scalar_one_or_none.return_value = mock_new_dl
        return mock_res

    mock_session.execute.side_effect = mock_execute

    with patch("app.core.link.LinkManager.check_links", new_callable=AsyncMock) as mock_check, \
         patch("app.services.enrichment_service.EnrichmentService.enrich_links", new_callable=AsyncMock) as mock_enrich, \
         patch("os.path.exists", return_value=True), \
         patch("os.remove") as mock_remove:

        mock_check.return_value = [mock_new_dl]

        response = await rescan_error(url="https://hoster.com/file1", db=mock_session)

        assert response["status"] == "success"
        assert "checked successfully" in response["message"]

        # Check updates to ScrapedURL
        assert mock_scraped.status == "success"
        assert mock_scraped.screenshot_path is None
        assert mock_scraped.html_path is None

        # Check remove calls
        assert mock_remove.call_count >= 2
        mock_session.commit.assert_called()

@pytest.mark.asyncio
async def test_rescan_error_fail():
    """Test rescan_error raises 400 when link check still fails."""
    mock_session = AsyncMock()

    mock_scraped = MagicMock(spec=ScrapedURL)
    mock_scraped.url = "https://hoster.com/file1"
    mock_scraped.source_name = "Hoster-Check"
    mock_scraped.status = "failed: original error"

    mock_dl = MagicMock(spec=DownloadLink)
    mock_dl.url = "https://hoster.com/file1"
    mock_dl.status = "error"

    mock_new_dl = MagicMock(spec=DownloadLink)
    mock_new_dl.url = "https://hoster.com/file1"
    mock_new_dl.status = "error"

    mock_latest_scraped = MagicMock(spec=ScrapedURL)
    mock_latest_scraped.status = "failed: new hoster error"

    dl_queries_count = 0
    scraped_queries_count = 0
    async def mock_execute(query, *args, **kwargs):
        nonlocal dl_queries_count, scraped_queries_count
        query_str = str(query)
        mock_res = MagicMock()
        if "FROM scraped_urls" in query_str or "scraped_urls" in query_str:
            scraped_queries_count += 1
            if scraped_queries_count == 1:
                mock_res.scalar_one_or_none.return_value = mock_scraped
            else:
                mock_res.scalar_one_or_none.return_value = mock_latest_scraped
        elif "FROM download_links" in query_str or "download_links" in query_str:
            if "IN (" in query_str:
                mock_res.all.return_value = []
            else:
                dl_queries_count += 1
                if dl_queries_count == 1:
                    mock_res.scalar_one_or_none.return_value = mock_dl
                else:
                    mock_res.scalar_one_or_none.return_value = mock_new_dl
        return mock_res

    mock_session.execute.side_effect = mock_execute

    with patch("app.core.link.LinkManager.check_links", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = [] # no new successful links

        with pytest.raises(HTTPException) as exc_info:
            await rescan_error(url="https://hoster.com/file1", db=mock_session)

        assert exc_info.value.status_code == 400
        assert "new hoster error" in exc_info.value.detail
