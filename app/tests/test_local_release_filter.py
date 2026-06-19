import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.release_service import ReleaseService

@pytest.mark.asyncio
async def test_get_grouped_releases_local_filter():
    # Mock database execute
    mock_session = AsyncMock()
    
    executed_queries = []
    
    async def mock_execute(query, *args, **kwargs):
        query_str = str(query)
        executed_queries.append(query_str)
        # Return a mock result with 0 total count and empty list
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_result.all.return_value = []
        mock_result.scalars.return_value.all.return_value = []
        return mock_result
        
    mock_session.execute.side_effect = mock_execute
    
    # 1. Test local=True
    await ReleaseService.get_grouped_releases(mock_session, local=True)
    # Verify that the query contains checking for local/null imdb_id
    assert any("imdb_id IS NULL" in q or "imdb_id = :imdb_id_1" in q or "LIKE" in q for q in executed_queries)
    
    executed_queries.clear()
    
    # 2. Test local=False
    await ReleaseService.get_grouped_releases(mock_session, local=False)
    # Verify that the query excludes local/null imdb_id
    assert any("imdb_id IS NOT NULL" in q or "NOT LIKE" in q for q in executed_queries)
    
    executed_queries.clear()
    
    # 3. Test local=None
    await ReleaseService.get_grouped_releases(mock_session, local=None)
    # Verify that the query does not check for like "local%" or NOT LIKE "local%"
    assert not any("LIKE" in q or "NOT LIKE" in q for q in executed_queries)
    
    print("[TEST] ReleaseService local release filter tested successfully!")
