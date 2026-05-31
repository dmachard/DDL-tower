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


@pytest.mark.asyncio
async def test_export_prunes_invalid_existing_releases():
    """Test that when existing releases are loaded from data.db.gz, invalid ones are pruned."""
    import gzip
    import json
    
    # Create valid and invalid dummy rows
    keys = ["title", "filename"]
    valid_row = ["Avatar", "Avatar.2009.mkv"]
    invalid_row = ["Junk", "MDMN65M4.rar"]
    
    dummy_db_data = {
        "keys": keys,
        "rows": [valid_row, invalid_row]
    }
    dummy_db_bytes = gzip.compress(json.dumps(dummy_db_data).encode("utf-8"))
    
    # We will mock open() to return dummy_db_bytes when reading data.db.gz
    # and capture whatever is written during export.
    mock_files = {}
    
    def mock_open_impl(filepath, mode="r", *args, **kwargs):
        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        if "r" in mode:
            if "data.db.gz" in filepath:
                mock_file.read.return_value = dummy_db_bytes
            else:
                mock_file.read.return_value = b""
        elif "w" in mode:
            def write_impl(data):
                mock_files[filepath] = data
            mock_file.write.side_effect = write_impl
        return mock_file
        
    with patch("app.cli.export.get_db_ctx") as mock_db_ctx, \
         patch("app.cli.export.settings") as mock_settings, \
         patch("os.path.exists", return_value=True), \
         patch("builtins.open", side_effect=mock_open_impl):
         
        mock_settings.DATA_EXPORT_DIR = "/app/data/export"
        mock_settings.GIT_ENABLED = False
        
        mock_session = AsyncMock()
        mock_db_ctx.return_value.__aenter__.return_value = mock_session
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result
        
        await ExportCommands.run_export(export_type="all")
        
        # Check that data.db.gz was written and contains the valid row but NOT the invalid row
        assert "/app/data/export/data.db.gz" in mock_files
        written_bytes = mock_files["/app/data/export/data.db.gz"]
        written_data = json.loads(gzip.decompress(written_bytes).decode("utf-8"))
        
        filename_idx = written_data["keys"].index("filename")
        written_filenames = [r[filename_idx] for r in written_data["rows"]]
        assert "Avatar.2009.mkv" in written_filenames
        assert "MDMN65M4.rar" not in written_filenames

