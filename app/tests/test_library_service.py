import pytest
from pathlib import Path
import os
from app.services.library_service import library_service

def test_series_folder_case_insensitivity(tmp_path, monkeypatch):
    """
    Test that if a series folder already exists with a different casing 
    (e.g., 'FROM (2022)' vs 'From (2022)'), the existing folder is reused 
    instead of creating a duplicate case-sensitive folder on Linux.
    """
    # Mock the series_dir to be our tmp_path
    monkeypatch.setattr(library_service, "series_dir", tmp_path)
    
    # 1. Create the original "FROM (2022)" folder manually 
    # (simulating an older download or user manual creation)
    existing_folder = tmp_path / "FROM (2022)"
    existing_folder.mkdir()
    
    # 2. Simulate organizing a new episode that has the title "From".
    # By default, title "From" + year "2022" => "From (2022)"
    # But because "FROM (2022)" already exists, it should reuse it!
    
    # Create a dummy file to organize
    source_file = tmp_path / "From.S01E01.mkv"
    source_file.write_text("dummy content")
    
    # Organize it
    success = library_service.organize_file(
        file_path=str(source_file),
        category="series",
        title="from",  # lowercase, will be .title() -> "From"
        year=2022,
        season=1,
        episode=1
    )
    
    assert success is True
    
    # 3. Check that it went into the EXISTING "FROM (2022)" folder
    expected_dest = existing_folder / "From.S01E01.mkv"
    assert expected_dest.exists(), "The file should be in the existing capitalized folder"
    
    # 4. Assert that no duplicate folder was created (case-sensitive check)
    new_folder = tmp_path / "From (2022)"
    # On Linux, this is a distinct path. It should NOT exist.
    assert not new_folder.exists() or new_folder == existing_folder, \
        "A new folder with different casing should NOT be created"

def test_movies_folder_cleanup(tmp_path, monkeypatch):
    """
    Test that older versions of a movie are deleted when a new one is organized.
    """
    monkeypatch.setattr(library_service, "movies_dir", tmp_path)
    
    old_version = tmp_path / "My.Movie.2023.720p.mkv"
    old_version.write_text("old content")
    
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    source_file = download_dir / "My.Movie.2023.1080p.mkv"
    source_file.write_text("new content")
    
    success = library_service.organize_file(
        file_path=str(source_file),
        category="movie",
        title="My Movie",
        year=2023
    )
    
    assert success is True
    assert not old_version.exists(), "Old version of the movie should be deleted"
    assert (tmp_path / "My.Movie.2023.1080p.mkv").exists(), "New version should be moved to movies_dir"
