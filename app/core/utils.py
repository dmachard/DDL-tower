import math
import re

def format_size(size_bytes: int) -> str:
    """Formats bytes to human readable string."""
    if size_bytes == 0: return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def parse_size(size_str: str) -> int:
    """Parses human readable string (e.g. '1.2 GB', '9,97 Go') to bytes."""
    if not size_str or size_str == "N/A" or size_str == "0B":
        return 0
    
    try:
        # Standardize decimal separator and split
        size_str = size_str.replace(",", ".").strip()
        parts = size_str.split()
        
        if len(parts) < 2:
            # Handle cases like "3.9GB" (no space)
            match = re.match(r'(\d+[.,]?\d*)\s*([a-zA-Z]+)', size_str)
            if match:
                value = float(match.group(1))
                unit = match.group(2).upper()
            else:
                return 0
        else:
            value = float(parts[0])
            unit = parts[1].upper()
        
        # Mapping French and English units
        units = {
            "B": 1,
            "KB": 1024, "KO": 1024,
            "MB": 1024**2, "MO": 1024**2,
            "GB": 1024**3, "GO": 1024**3,
            "TB": 1024**4, "TO": 1024**4
        }
        
        return int(value * units.get(unit, 1))
    except (ValueError, IndexError):
        return 0

def get_quality_score(resolution: str = None, language: str = None, v_quality: str = None, quality: str = None, audio: str = None) -> int:
    """Returns a numeric score for quality comparison (Resolution > Language > Video Quality > Audio > Source)."""
    score = 0
    
    # 1. Resolution
    res = (resolution or "").lower()
    if "4klight" in res: score += 450
    elif "2160" in res or "4k" in res: score += 400
    elif "1080" in res: score += 300
    elif "720" in res: score += 200
    elif "480" in res: score += 100
    
    # 2. Language (Multi > VF > VOST)
    lang = (language or "").lower()
    if "multi" in lang: score += 50
    elif any(x in lang for x in ["vff", "vfq", "vf"]): score += 30
    elif "vost" in lang or "subforced" in lang: score += 10
    
    # 3. Video Quality (HDR / 10bit)
    vq = (v_quality or "").lower()
    if "hdr" in vq: score += 20
    if "10bit" in vq: score += 10
    
    # 4. Audio Quality (Atmos / TrueHD / DTS > AC3)
    aud = (audio or "").lower()
    if "atmos" in aud or "truehd" in aud: score += 15
    elif "dts" in aud: score += 10
    elif "ac3" in aud or "dd5" in aud or "dd2" in aud: score += 5

    # 5. Source Quality (BluRay > WEB-DL > HDTV)
    q = (quality or "").lower()
    if "bluray" in q or "bdrip" in q: score += 10
    elif "web" in q: score += 7
    elif "hdtv" in q: score += 3
    
    return score
