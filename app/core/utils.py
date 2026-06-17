import math
import re
import unicodedata

def normalize_title(title: str) -> str:
    """
    Normalizes a title for robust duplicate matching.
    Strips accents, converts to lowercase, removes punctuation and extra spaces.
    """
    if not title:
        return ""
    title_str = str(title)
    # Strip accents
    normalized = unicodedata.normalize('NFKD', title_str)
    ascii_title = normalized.encode('ASCII', 'ignore').decode('utf-8')
    # Replace non-alphanumeric characters with spaces to avoid joining words
    cleaned = re.sub(r'[^a-z0-9]', ' ', ascii_title.lower())
    # Collapse multiple spaces and strip
    return re.sub(r'\s+', ' ', cleaned).strip()

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

def get_quality_score(resolution: str = None, language: str = None, v_quality: str = None, quality: str = None, audio: str = None, codec: str = None) -> int:
    """Returns a numeric score for quality comparison (Resolution > Language > Video Quality > Audio > Source > Codec)."""
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
    
    # 6. Codec (HEVC / x265 > x264)
    c = (codec or "").lower()
    if "265" in c or "hevc" in c: score += 5
    
    return score

async def save_error_dump(url: str, page) -> tuple:
    """
    Saves a screenshot and HTML dump of the current playwright page.
    Returns (screenshot_relative_path, html_relative_path).
    """
    import os
    import time
    import hashlib
    import traceback
    try:
        os.makedirs("data/error_dumps", exist_ok=True)
        
        # Unique identifier from URL + timestamp
        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
        timestamp = int(time.time() * 1000)
        filename_base = f"{timestamp}_{url_hash}"
        
        screenshot_rel = f"/static/error_dumps/screenshot_{filename_base}.png"
        html_rel = f"/static/error_dumps/html_{filename_base}.html"
        
        screenshot_abs = f"data/error_dumps/screenshot_{filename_base}.png"
        html_abs = f"data/error_dumps/html_{filename_base}.html"
        
        screenshot_path = None
        html_path = None
        
        # Take screenshot
        try:
            await page.screenshot(path=screenshot_abs, full_page=True, timeout=10000)
            screenshot_path = screenshot_rel
        except Exception as se:
            print(f"[ERROR-DUMP] Failed to save full page screenshot: {se}")
            # Try viewport screenshot as fallback
            try:
                await page.screenshot(path=screenshot_abs, full_page=False, timeout=5000)
                screenshot_path = screenshot_rel
            except Exception as se2:
                print(f"[ERROR-DUMP] Failed to save fallback viewport screenshot: {se2}")
        
        # Save HTML
        try:
            content = await page.content()
            with open(html_abs, "w", encoding="utf-8") as f:
                f.write(content)
            html_path = html_rel
        except Exception as he:
            print(f"[ERROR-DUMP] Failed to save HTML: {he}")
            
        return screenshot_path, html_path
    except Exception as e:
        print(f"[ERROR-DUMP] General failure: {e}")
        traceback.print_exc()
        return None, None
