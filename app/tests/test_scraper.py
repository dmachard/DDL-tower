import pytest
import re
import json
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.scraper import Scraper

@pytest.fixture
def scraper():
    return Scraper({"name": "TestScraper"})

def test_render_string(scraper):
    """Test Jinja2 rendering in scraper."""
    context = {"discovery": {"title": "Matrix"}, "page": 2}
    assert scraper._render_string("Search for {{ discovery.title }}", context) == "Search for Matrix"
    assert scraper._render_string("Page {{ page + 1 }}", context) == "Page 3"

def test_update_url_param_query(scraper):
    """Test updating query parameters for pagination."""
    url = "https://api.com/search?q=test"
    new_url = scraper._update_url_param(url, "page", 2)
    assert "page=2" in new_url
    assert "q=test" in new_url

def test_update_url_param_path(scraper):
    """Test updating path-based pagination (e.g. /page/2/)."""
    url = "https://site.com/films/"
    new_url = scraper._update_url_param(url, "/page", 2)
    assert new_url == "https://site.com/films/page/2/"

def test_extract_json(scraper):
    """Test JSONPath extraction."""
    content = '{"results": [{"title": "A"}, {"title": "B"}]}'
    results = scraper._extract_json(content, "$.results[*]")
    assert len(results) == 2
    assert results[0]["title"] == "A"

def test_extract_rss(scraper):
    """Test RSS feed parsing."""
    content = """<?xml version="1.0" encoding="UTF-8" ?>
    <rss version="2.0">
    <channel>
      <item><title>Movie 1</title><link>http://site.com/1</link></item>
      <item><title>Movie 2</title><link>http://site.com/2</link></item>
    </channel>
    </rss>"""
    results = scraper._extract_rss(content)
    assert len(results) == 2
    assert results[0]["title"] == "Movie 1"

def test_link_extraction_patterns(scraper):
    """Test the real _extract_links method of the Scraper."""
    html = '<a href="https://1fichier.com/?abc123def">Link</a>'
    patterns = [r'https?://1fichier\.com/\?[^"\s<]+']
    found = scraper._extract_links(html, patterns)
    assert len(found) == 1
    assert "abc123def" in found[0]

def test_keyword_filtering(scraper):
    """Test the real _matches_keywords method of the Scraper."""
    text = "The Matrix 1080p MULTI"
    required = {"1080p": "HD"}
    excluded = ["SD"]
    
    tags = scraper._matches_keywords(text, required, excluded)
    assert tags == ["HD"]
    assert scraper._matches_keywords("The Matrix 720p SD", required, excluded) is None

def test_hoster_pattern_matching(scraper):
    """Test the real _is_hoster_link method of the Scraper."""
    hoster_patterns = [r'https?://(?:www\.)?1fichier\.com/\?[^\s"\'<>]+']
    assert scraper._is_hoster_link("https://1fichier.com/?abcdef", hoster_patterns) is True
    assert scraper._is_hoster_link("https://google.com", hoster_patterns) is False

@pytest.mark.asyncio
async def test_execute_step_with_list_url():
    """High-level test: Validate _execute_step handles a list of URLs without crashing."""
    config = {
        "name": "TestList",
        "steps": [
            {
                "name": "step1",
                "url": ["https://site1.com", "https://site2.com"],
                "type": "html"
            }
        ]
    }
    scraper = Scraper(config)
    
    # Mock httpx client
    client = MagicMock()
    client.get = AsyncMock()
    
    # Mock response
    mock_resp = MagicMock()
    mock_resp.text = "<html>Links</html>"
    mock_resp.raise_for_status = MagicMock()
    client.get.return_value = mock_resp

    # Execute step
    results = []
    async for batch in scraper._execute_step(client, 0, [{}]):
        results.append(batch)
    
    # Should have called get twice
    assert client.get.call_count == 2

@pytest.mark.asyncio
async def test_execute_step_context_inheritance():
    """Test that Step 2 inherits the title from Step 1 context."""
    config = {
        "name": "TestInherit",
        "steps": [
            {
                "name": "step1",
                "url": "https://site.com/1",
                "regex_patterns": [r'https?://site\.com/2'],
                "override_title": "Original Title"
            },
            {
                "name": "step2",
                "url": "{{ step1.url }}",
                "yield_links": True,
                "hoster_patterns": [r'https?://1fichier\.com/\?\w+']
            }
        ]
    }
    scraper = Scraper(config)
    client = MagicMock()
    client.get = AsyncMock()
    
    # Step 1 response
    resp1 = MagicMock()
    resp1.text = "Follow this: https://site.com/2"
    
    # Step 2 response
    resp2 = MagicMock()
    resp2.text = "Download: https://1fichier.com/?file123"
    
    client.get.side_effect = [resp1, resp2]

    results = []
    async for batch in scraper._execute_step(client, 0, [{}]):
        results.append(batch)
    
    assert len(results) == 1
    assert results[0]["override_title"] == "Original Title"
    assert "file123" in results[0]["links"][0]

@pytest.mark.asyncio
async def test_pagination_infinite_loop_protection():
    """Test that scraper stops if content doesn't change between pages."""
    config = {
        "name": "TestLoop",
        "steps": [
            {
                "name": "step1",
                "url": "https://site.com/page/1",
                "pagination": {"param": "page", "max_pages": 10}
            }
        ]
    }
    scraper = Scraper(config)
    client = MagicMock()
    client.get = AsyncMock()
    
    # Always return the same content
    mock_resp = MagicMock()
    mock_resp.text = "Same Content Every Time"
    client.get.return_value = mock_resp

    results = []
    async for batch in scraper._execute_step(client, 0, [{}]):
        results.append(batch)
    
    # Should have called get twice (Page 1, then Page 2 which is same as Page 1 -> break)
    # Note: the first page hash is stored, then the second page is fetched and compared.
    assert client.get.call_count == 2


@pytest.mark.asyncio
async def test_dict_item_link_extraction():
    """Test that dictionary items use 'url' or 'href' directly without mangling."""
    config = {
        "name": "TestDict",
        "steps": [
            {
                "name": "step1",
                "url": "https://site.com",
                "yield_links": True
            }
        ]
    }
    scraper = Scraper(config)
    client = MagicMock()
    
    # Simulate a dictionary item returned by js_code (e.g. from detail step)
    item = {"href": "https://protect.link/abc", "provider": "xxxx"}
    
    results = []
    # We call _handle_item directly to test the extraction logic
    async for batch in scraper._handle_item(client, item, config["steps"][0], {}, 0, "https://site.com", ""):
        results.append(batch)
        
    assert len(results) == 1
    # Check that it extracted ONLY the href, without the rest of the dictionary
    assert results[0]["links"][0] == "https://protect.link/abc"
@pytest.mark.asyncio
async def test_bulk_scrape_once_skip():
    """Test that URLs marked as scrape_once are skipped in bulk before navigation."""
    config = {
        "name": "TestBulk",
        "steps": [
            {
                "name": "step1",
                "url": ["https://new.com", "https://already_scraped.com"],
                "scrape_once": True
            }
        ]
    }
    scraper = Scraper(config)
    client = MagicMock()
    mock_resp = AsyncMock()
    mock_resp.raise_for_status = MagicMock() 
    mock_resp.text = AsyncMock(return_value="<html></html>")
    mock_resp.status = 200
    mock_resp.__aenter__.return_value = mock_resp
    client.get.return_value = mock_resp
    
    # Mock database to say one URL is already scraped
    with patch("app.core.scraper.get_db_ctx") as mock_db_ctx:
        mock_session = AsyncMock()
        mock_db_ctx.return_value.__aenter__.return_value = mock_session
        
        # Mock result for SELECT url FROM scraped_urls WHERE url IN (...)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = ["https://already_scraped.com"]
        mock_session.execute.return_value = mock_result
        
        results = []
        async for batch in scraper._execute_step(client, 0, [{}]):
            results.append(batch)
            
        # Verify that client.get was only called for the NEW url
        assert client.get.call_count == 1
        args, _ = client.get.call_args
        assert args[0] == "https://new.com"
        print("[TEST] Bulk scrape_once skip verified.")

def test_deduplicate_links(scraper):
    """Test that scraper deduplicates URLs by ID and extension."""
    links = [
        "https://rapidgator.net/file/4bc1a631/file.part1.rar.html",
        "https://rapidgator.net/file/4bc1a631/file.part1.rar",
        "https://1fichier.com/?abc123def&html=1",
        "https://1fichier.com/?abc123def"
    ]
    cleaned = scraper._deduplicate_links(links)
    assert len(cleaned) == 2
    assert "https://rapidgator.net/file/4bc1a631/file.part1.rar" in cleaned
    assert "https://1fichier.com/?abc123def" in cleaned
    assert not any(l.endswith(".html") for l in cleaned)
