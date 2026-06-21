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

@pytest.mark.asyncio
async def test_unlock_extracts_using_capture_groups():
    unlocker = LinkUnlocker()
    
    mock_browser = MagicMock()
    mock_page = MagicMock()
    mock_page.url = "https://multiup.io/en/mirror/abc"
    mock_page.title = AsyncMock(return_value="Page Title")
    mock_page.content = AsyncMock(return_value='<html><body><a href="https://1fichier.com/?abcdef">Link</a></body></html>')
    mock_page.goto = AsyncMock()
    mock_page.close = AsyncMock()
    
    mock_page.screenshot = AsyncMock(return_value=b"")
    
    mock_locator = MagicMock()
    mock_locator.first = MagicMock()
    mock_locator.first.is_visible = AsyncMock(return_value=True)
    mock_locator.first.wait_for = AsyncMock()
    mock_locator.count = AsyncMock(return_value=0)
    mock_page.locator.return_value = mock_locator
    
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.is_connected = MagicMock(return_value=True)
    
    with patch("app.services.unlocker.async_playwright") as mock_pw, \
         patch("app.services.browser_manager.browser_manager") as mock_bm, \
         patch("app.services.unlocker.settings") as mock_settings:
         
        mock_pw_context = MagicMock()
        mock_pw_context.__aenter__ = AsyncMock(return_value=MagicMock())
        mock_pw.return_value = mock_pw_context
        
        mock_bm.get_browser = AsyncMock(return_value=mock_browser)
        
        # Explicitly configure unlockers for this unit test to run independently of config.yaml
        mock_settings.UNLOCKERS = [
            {
                "name": "MultiUp",
                "patterns": [r'https?://(?:www\.)?multiup\.(?:io|org)/[^\s"\'<>]+'],
                "wait_delay": 0,
                "mirror_selector": 'a[href*="/mirror/"], form[action*="/mirror/"]',
                "skip_turnstile": False,
                "wait_for_final": "a[href*='1fichier.com']"
            }
        ]
        extra_patterns = [r'href=["\'](https?://(?:www\.)?1fichier\.com/\?[\w-]+)[^"\']*["\']']
        
        links = await unlocker.unlock("https://multiup.io/download/abc/file.mkv", extra_patterns=extra_patterns)
        assert links == ["https://1fichier.com/?abcdef"]


