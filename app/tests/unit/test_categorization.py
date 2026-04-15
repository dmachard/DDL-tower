import pytest
from app.core.categorization import Categorizer

@pytest.mark.parametrize("original, expected", [
    ("La legende de Zatoichi Vol4 Voyage en enfer", "La legende de Zatoichi Voyage en enfer"),
    ("Matrix.Reloaded.Vol.2", "Matrix Reloaded"),
    ("The_Batman_Part_I", "The Batman Part I"),
    ("Integrale_Stargate_SG1_Pack", "Stargate SG1"),
    ("The.Godfather.Pt.1", "The Godfather"),
    ("The.Godfather.Pt1", "The Godfather"),
    ("Stargate.SG1.S01.INTEGRALE", "Stargate SG1 S01"),
    ("Mission.Impossible.Dead.Reckoning.Part.One", "Mission Impossible Dead Reckoning"),
    ("Le Parrain, 2e partie", "Le Parrain"),
    ("Kaamelott Deuxieme volet Partie 1", "Kaamelott Deuxieme volet"),
    ("Volume 5 - Alien", "Alien"),
    ("Le Nom de la Rose 1986", "Le Nom de la Rose"),
])
def test_clean_search_title(original, expected):
    """Test that titles are cleaned correctly for search engines."""
    assert Categorizer._clean_search_title(original) == expected

def test_clean_search_title_empty():
    """Test handling of empty or None titles."""
    assert Categorizer._clean_search_title("") == ""
    assert Categorizer._clean_search_title(None) is None

@pytest.mark.parametrize("title_noise", [
    "Vol 1", "Vol. 1", "Volume 1", "Part 1", "Pt 1", "Partie 1", "Pack", "Integrale", "Intégrale"
])
def test_clean_search_title_individual_patterns(title_noise):
    """Test that individual noise patterns are removed."""
    title = f"Movie Title {title_noise}"
    assert Categorizer._clean_search_title(title) == "Movie Title"

@pytest.mark.parametrize("original, expected", [
    ("Disney Plus", "Disney+"),
    ("Amazon Studios", "Amazon"),
    ("HBO Max", "HBO"),
    ("Apple TV Plus", "Apple TV+"),
    ("Netflix", "Netflix"),
    (None, None),
    ("", ""),
])
def test_clean_network_name(original, expected):
    """Test that network names are normalized."""
    assert Categorizer._clean_network_name(original) == expected

@pytest.mark.parametrize("filename, expected", [
    ("Malcolm.in.the.Middle.Lifes.Still.Unfair.S01.2160p.DSNP.WEB-DL.DDP5.1.DV.HDR.H.265-FLUX", "HDR DV"),
    ("Malcolm.in.the.Middle.Lifes.Still.Unfair.S01.HDR.2160p.WEB-DL.DDP5.1.H.265-ETHEL", "HDR"),
    ("Malcolm.in.the.Middle.Lifes.Still.Unfair.S01.2160p.DSNP.WEB-DL.DDP5.1.DV.H.265-FLUX", "DV"),
    ("Malcolm.in.the.Middle.Life’s.Still.Unfair.S01.2160p.DSNP.WEB-DL.DD+5.1.DoVi.H.265-playWEB", "DV"),
    ("Extraction.2.2023.2160p.NF.WEB-DL.DDP5.1.Atmos.HDR10.HEVC-DDP", "HDR"),
    ("Planet.Earth.III.S01E01.2160p.iP.WEB-DL.DDP5.1.HLG.H.265-FLUX", "HLG"),
    ("Malcolm.in.the.Middle.Lifes.Still.Unfair.S01.1080p.WEB-DL.DDP5.1.H.264-ETHEL", None),
])
def test_extract_v_quality(filename, expected):
    """Test HDR/DV detection from filenames."""
    assert Categorizer._extract_v_quality(filename) == expected
