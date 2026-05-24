import pytest
from app.core.utils import get_quality_score

def test_resolution_ranking():
    # 4Klight > 4K > 1080p > 720p
    assert get_quality_score(resolution="4klight") > get_quality_score(resolution="4k")
    assert get_quality_score(resolution="2160p") > get_quality_score(resolution="1080p")
    assert get_quality_score(resolution="1080p") > get_quality_score(resolution="720p")
    assert get_quality_score(resolution="4k") == get_quality_score(resolution="2160p")

def test_language_ranking():
    # Multi > VF > VOST
    base_res = "1080p"
    multi = get_quality_score(resolution=base_res, language="MULTI")
    vf = get_quality_score(resolution=base_res, language="VFF")
    vost = get_quality_score(resolution=base_res, language="VOSTFR")
    
    assert multi > vf
    assert vf > vost
    assert multi > vost

def test_audio_ranking():
    # Atmos > DTS > AC3
    base_res = "1080p"
    atmos = get_quality_score(resolution=base_res, audio="Atmos")
    dts = get_quality_score(resolution=base_res, audio="DTS")
    ac3 = get_quality_score(resolution=base_res, audio="AC3")
    
    assert atmos > dts
    assert dts > ac3

def test_video_extras():
    # HDR > 10bit
    base_res = "1080p"
    hdr = get_quality_score(resolution=base_res, v_quality="HDR")
    tenbit = get_quality_score(resolution=base_res, v_quality="10bit")
    none = get_quality_score(resolution=base_res)
    
    assert hdr > tenbit
    assert tenbit > none

def test_complex_upgrade():
    # User's specific cases:
    # Multi+4khdr > 1080p multi > 1080p vost
    
    score_4k_hdr_multi = get_quality_score(resolution="2160p", v_quality="HDR", language="MULTI")
    score_1080_multi = get_quality_score(resolution="1080p", language="MULTI")
    score_1080_vost = get_quality_score(resolution="1080p", language="VOSTFR")
    
    assert score_4k_hdr_multi > score_1080_multi
    assert score_1080_multi > score_1080_vost

def test_source_ranking():
    # BluRay > WEB-DL > HDTV
    base_res = "1080p"
    bluray = get_quality_score(resolution=base_res, quality="BluRay")
    web = get_quality_score(resolution=base_res, quality="WEB-DL")
    hdtv = get_quality_score(resolution=base_res, quality="HDTV")
    
    assert bluray > web
    assert web > hdtv

def test_null_handling():
    # Should not crash with None values
    assert get_quality_score(None, None, None, None, None, None) == 0

def test_equal_quality():
    # User's specific cases:
    from app.services.parser_service import parser_service
    
    f1 = "Si.J.En.2025.MULTi.VFF.2160p.DV.HDR.WEB.EAC3.5.1.H265-TFA.mkv"
    f2 = "Si.J.En.2025.MULTi.VFF.2160p.DV.HDR.WEB.EAC3.5.1.H265-TFA.WIN.mkv"
    
    res1 = parser_service.parse_filename(f1)
    res2 = parser_service.parse_filename(f2)
    
    score1 = get_quality_score(
        resolution=res1.get("resolution"),
        quality=res1.get("quality"),
        v_quality=res1.get("v_quality"),
        audio=res1.get("audio"),
        language=" ".join(res1.get("languages", [])),
        codec=res1.get("codec")
    )
    
    score2 = get_quality_score(
        resolution=res2.get("resolution"),
        quality=res2.get("quality"),
        v_quality=res2.get("v_quality"),
        audio=res2.get("audio"),
        language=" ".join(res2.get("languages", [])),
        codec=res2.get("codec")
    )
    
    # Both should have exactly the same score because Wawacity.WIN is just a release group suffix
    assert score1 == score2

def test_codec_score():
    from app.services.parser_service import parser_service
    
    f1 = "Un.balco.2020.VOF.1080p.WEBRip.EAC3.2.0.x264-Fist.WIN.mkv"
    f2 = "Un Balcon (2020) Vof.1080P.Webrip.Eac3.X265-ParadiZe.mkv"
    
    res1 = parser_service.parse_filename(f1)
    res2 = parser_service.parse_filename(f2)
    
    score1 = get_quality_score(
        resolution=res1.get("resolution"),
        quality=res1.get("quality"),
        v_quality=res1.get("v_quality"),
        audio=res1.get("audio"),
        language=" ".join(res1.get("languages", [])),
        codec=res1.get("codec")
    )
    
    score2 = get_quality_score(
        resolution=res2.get("resolution"),
        quality=res2.get("quality"),
        v_quality=res2.get("v_quality"),
        audio=res2.get("audio"),
        language=" ".join(res2.get("languages", [])),
        codec=res2.get("codec")
    )
    
    # score2 should be greater because it's x265
    assert score2 > score1


