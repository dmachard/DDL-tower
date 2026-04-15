import pytest
from app.services.parser_service import parser_service

@pytest.mark.parametrize("original, expected", [
    ("La legende de Zatoichi Vol4 Voyage en enfer", "La legende de Zatoichi Voyage en enfer"),
    ("Matrix.Reloaded.Vol.2", "Matrix Reloaded"),
    ("The.Godfather.Pt.1", "The Godfather"),
    ("Le Parrain, 2e partie", "Le Parrain"),
    ("Le Nom de la Rose 1986", "Le Nom de la Rose"),
])
def test_clean_search_title(original, expected):
    """Test that titles are cleaned correctly for search engines."""
    assert parser_service.clean_search_title(original) == expected

@pytest.mark.parametrize("original, expected", [
    ("Disney Plus", "Disney+"),
    ("Amazon Studios", "Amazon"),
    ("HBO Max", "HBO"),
    (None, None),
])
def test_clean_network_name(original, expected):
    """Test that network names are normalized."""
    assert parser_service.clean_network_name(original) == expected

@pytest.mark.parametrize("filename, expected", [
    ("Movie.DV.HDR.2160p.mkv", "HDR DV"),
    ("Movie.HDR.2160p.mkv", "HDR"),
    ("Movie.Dolby.Vision.2160p.mkv", "DV"),
    ("Movie.1080p.mkv", None),
])
def test_extract_v_quality(filename, expected):
    """Test HDR/DV detection from filenames."""
    assert parser_service.extract_v_quality(filename) == expected

def test_parse_filename_movie():
    """Test parsing a movie filename."""
    filename = "Interstellar.2014.ENGLISH.2160p.WEB-DL.DDP5.1.HDR.HEVC-DDP.mkv"
    res = parser_service.parse_filename(filename)
    assert res["title"] == "Interstellar"
    assert res["category"] == "movie"
    assert res["year"] == 2014
    assert res["resolution"] == "2160p"
    assert res["v_quality"] == "HDR"
    assert "ENGLISH" in [l.upper() for l in res["languages"]]

def test_parse_filename_series():
    """Test parsing a series filename."""
    filename = "The.Mandalorian.S02E01.Chapter.9.The.Marshal.2160p.DSNP.WEB-DL.DDP5.1.Atmos.DV.HDR.HEVC-FLUX.mkv"
    res = parser_service.parse_filename(filename)
    assert res["title"] == "The Mandalorian"
    assert res["category"] == "series"
    assert res["season"] == "2"
    assert res["episode"] == "1"
    assert res["network"] == "Disney+"
    assert "DV" in res["v_quality"]
    assert "HDR" in res["v_quality"]

def test_parse_filename_multi_vostfr():
    """Test parsing a filename with MULTI and VOSTFR."""
    filename = "Movie.2023.MULTI.VOSTFR.1080p.mkv"
    res = parser_service.parse_filename(filename)
    langs = [l.upper() for l in res["languages"]]
    assert "MULTI" in langs
    assert "VOSTFR" in langs
