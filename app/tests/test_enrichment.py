import pytest
from unittest.mock import AsyncMock, patch
from app.services.enrichment_service import EnrichmentService
from app.db.models import DownloadLink

@pytest.mark.asyncio
@pytest.mark.parametrize("scenario, scraper_title, filename, category, expected_title", [
    ("Tracker Case (Series Mismatch)", "Alan Davies: As Yet Untitled", "Tracker.S03E13.1080p.mkv", "series", "Tracker"),
    ("HDEncode Case (Obfuscated File)", "Clika", "Cia22100NFWBLDD51AmsH264layEB.rar", "movie", "Clika"),
    ("LOTR Case (Movie Acronym)", "Le Seigneur des Anneaux", "LOTR.2001.mkv", "movie", "Le Seigneur des Anneaux"),
    ("BCS Case (Series Acronym)", "Better Call Saul", "BCS.S01E01.mkv", "series", "BCS"),
    ("Obfuscated Series Case", "Tracker", "Cia22100.S03E13.1080p.mkv", "series", "Tracker"),
])
async def test_title_resolution(scenario, scraper_title, filename, category, expected_title):
    """
    Test scenario: {{ scenario }}
    """
    # Mock session
    session = AsyncMock()
    
    link = DownloadLink(
        title=scraper_title,
        filename=filename,
        category=category
    )
    
    links = [link]
    
    # Mock the actual enrichment call to avoid DB/API interaction
    with patch("app.services.enrichment_service.EnrichmentService.enrich_link_metadata", new_callable=AsyncMock):
        await EnrichmentService.process_batch(session, links)
    
    assert link.title == expected_title, f"Failed {scenario}: expected '{expected_title}', got '{link.title}'"
