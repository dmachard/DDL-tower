import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.enrichment_service import EnrichmentService
from app.db.models import DownloadLink

@pytest.mark.asyncio
async def test_enrichment_obfuscated_filename_preservation():
    """Test that enrichment preserves scraper title even if filename is obfuscated (RotrS1 vs Rooster)."""
    session = AsyncMock()
    
    # Case: HDEncode feed title vs obfuscated filename
    link = DownloadLink(
        id=1,
        title="Rooster S01E09 Ludlows Fourth Hottest Professor 2160p HMAX WEB-DL DDP5.1 Atmos H.265-RAWR",
        filename="RotrS1E9LulwsFutHttstPoessor210pHAWELDD5AmsH25AR.rar",
        source_name="source",
        category="series"
    )
    
    # Patch enrich_link_metadata to avoid DB calls
    with patch("app.services.enrichment_service.EnrichmentService.enrich_link_metadata", new_callable=AsyncMock):
        await EnrichmentService.process_batch(session, [link])
    
    # The title should be "Rooster" (cleaned from scraper title)
    # NOT "RotrS1" (cleaned from filename)
    assert link.title == "Rooster"
    assert link.season == "1"
    assert link.episode == "9"

@pytest.mark.asyncio
async def test_enrichment_fallback_to_filename_when_no_title():
    """Test that enrichment falls back to filename if no scraper title is provided."""
    session = AsyncMock()
    
    link = DownloadLink(
        id=2,
        title=None,
        filename="The.Matrix.1999.1080p.BluRay.x264.mkv",
        source_name="Manual"
    )
    
    with patch("app.services.enrichment_service.EnrichmentService.enrich_link_metadata", new_callable=AsyncMock):
        await EnrichmentService.process_batch(session, [link])
    
    assert link.title == "The Matrix"
    assert link.year == 1999
    assert link.resolution == "1080p"

@pytest.mark.asyncio
async def test_enrichment_short_scraper_title_preservation():
    """Test that enrichment preserves even short scraper titles if explicitly provided."""
    session = AsyncMock()
    
    link = DownloadLink(
        id=3,
        title="Hi", # Short but explicitly provided
        filename="Breaking.Bad.S01E01.1080p.mkv",
        source_name="GenericSource"
    )
    
    with patch("app.services.enrichment_service.EnrichmentService.enrich_link_metadata", new_callable=AsyncMock):
        await EnrichmentService.process_batch(session, [link])
    
    # Should KEEP "Hi" because it was the explicit title
    assert link.title == "Hi"
    assert link.season == "1" # Technical info still merged from filename
