import pytest
from app.core.categorization import Categorizer

@pytest.mark.parametrize("original, expected", [
    ("Le Nom de la Rose 1986", "Le Nom de la Rose"),
])
def test_clean_search_title(original, expected):
    """Test that titles are cleaned correctly via the facade."""
    assert Categorizer._clean_search_title(original) == expected

@pytest.mark.parametrize("original, expected", [
    ("Disney Plus", "Disney+"),
])
def test_clean_network_name(original, expected):
    """Test that network names are normalized via the facade."""
    assert Categorizer._clean_network_name(original) == expected

@pytest.mark.parametrize("filename, expected", [
    ("Malcolm.in.the.Middle.S01.2160p.DV.HDR.mkv", "HDR DV"),
])
def test_extract_v_quality(filename, expected):
    """Test HDR/DV detection via the facade."""
    assert Categorizer._extract_v_quality(filename) == expected
