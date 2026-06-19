import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.unlocker import LinkUnlocker

@pytest.mark.asyncio
async def test_click_via_template_matching_bypassed_immediately():
    unlocker = LinkUnlocker()
    mock_page = MagicMock()
    
    mock_locator = MagicMock()
    mock_locator.first = MagicMock()
    mock_locator.first.is_visible = AsyncMock(return_value=True)
    mock_page.locator.return_value = mock_locator

    res = await unlocker._click_via_template_matching(
        page=mock_page,
        bypass_selectors=[".success-links"],
        max_wait_seconds=2,
        poll_interval=0.1
    )
    assert res is True
    # page.screenshot should not be called because we bypassed template matching immediately
    mock_page.screenshot.assert_not_called()

@pytest.mark.asyncio
async def test_click_via_template_matching_bypassed_during_polling():
    unlocker = MagicMock()
    unlocker._click_via_template_matching = LinkUnlocker._click_via_template_matching
    mock_page = MagicMock()
    
    mock_page.screenshot = AsyncMock(return_value=b"some_bytes")
    
    mock_locator = MagicMock()
    mock_locator.first = MagicMock()
    mock_locator.first.is_visible = AsyncMock()
    # Return False on first poll check, then True on second
    mock_locator.first.is_visible.side_effect = [False, True]
    mock_page.locator.return_value = mock_locator
    
    with patch("app.services.unlocker.find_template") as mock_find_template:
        mock_match = MagicMock()
        mock_match.found = False
        mock_match.confidence = 0.1
        mock_find_template.return_value = mock_match
        
        res = await unlocker._click_via_template_matching(
            unlocker,
            page=mock_page,
            bypass_selectors=[".success-links"],
            max_wait_seconds=5,
            poll_interval=0.1
        )
        assert res is True
        assert mock_page.screenshot.call_count == 1
