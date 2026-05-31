import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from app.cli.export import ExportCommands
from app.db.models import DownloadLink

@pytest.mark.asyncio
async def test_export_git_filtering_stats_only():
    """Test that when GIT_EXPORT_TYPE is 'stats', only stats.db.gz is copied and pushed to Git."""
    with patch("app.cli.export.get_db_ctx") as mock_db_ctx, \
         patch("app.cli.export.run_git_cmd") as mock_git_cmd, \
         patch("app.cli.export.check_needs_push", return_value=True), \
         patch("app.cli.export.settings") as mock_settings, \
         patch("os.path.exists", return_value=True), \
         patch("os.path.isdir", return_value=True), \
         patch("builtins.open", new_callable=MagicMock) as mock_open:
         
        mock_settings.DATA_EXPORT_DIR = "/app/data/export"
        mock_settings.GIT_ENABLED = True
        mock_settings.GIT_REPO_URL = "https://github.com/user/repo"
        mock_settings.GIT_BRANCH = "data_test"
        mock_settings.GIT_CLONE_DIR = "data/git_export"
        mock_settings.GIT_EXPORT_TYPE = "stats"  # Stats only!
        
        mock_session = AsyncMock()
        mock_db_ctx.return_value.__aenter__.return_value = mock_session
        
        # Mock empty database links to make test run fast
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        
        # Execute the export command
        await ExportCommands.run_export(export_type="all")
        
        # Check files that were written to the Git target directory.
        written_files = []
        for call in mock_open.call_args_list:
            args, kwargs = call
            filepath = args[0]
            if "git_export" in filepath:
                written_files.append(filepath)
                
        assert any("stats.db.gz" in f for f in written_files)
        assert not any("data.db.gz" in f for f in written_files)
