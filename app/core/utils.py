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
