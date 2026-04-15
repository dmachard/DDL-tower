import PTN
import re
import html
from typing import Optional, Dict, Any

class ParserService:
    @staticmethod
    def clean_network_name(name: str) -> str:
        """Normalizes network names for better UI display."""
        if not name:
            return name
        
        mapping = {
            "Disney Plus": "Disney+",
            "Amazon Studios": "Amazon",
            "Amazon Prime": "Amazon",
            "HBO Max": "HBO",
            "Apple TV Plus": "Apple TV+",
            "Paramount Plus": "Paramount+"
        }
        return mapping.get(name, name)

    @staticmethod
    def extract_v_quality(filename: str) -> Optional[str]:
        """Detects HDR, DV, etc. from filename."""
        if not filename:
            return None
        
        fn = filename.upper()
        tags = []
        
        # Check for Dolby Vision (flexible search for DV, DOVI, Dolby Vision)
        if any(x in fn for x in ["DV", "DOVI"]) or re.search(r'DOLBY[\.\-\s]VISION', fn):
            tags.append("DV")
        if any(x in fn for x in ["HDR", "HDR10", "HDR10PLUS", "HDR10+"]):
            tags.append("HDR")
        if "HLG" in fn:
            tags.append("HLG")
            
        if not tags:
            return None
            
        return " ".join(sorted(list(set(tags)), reverse=True))

    @staticmethod
    def clean_search_title(title: str) -> str:
        """Cleans the title for better TMDb matching."""
        if not title:
            return title
            
        t = title.replace('.', ' ').replace('_', ' ')
        t = re.sub(r'\b(vol|volume|part|partie|pt)\.?\s*\d+\b', '', t, flags=re.I)
        t = re.sub(r'\b\d+(?:er|e|eme|ème)\s+(?:partie|volet)\b', '', t, flags=re.I)
        t = re.sub(r'\b(?:part|pt)\.?\s+(?:one|two|three|four|five|six|seven|eight|nine|ten)\b', '', t, flags=re.I)
        t = re.sub(r'\b(int[ée]grale|pack|complet)\b', '', t, flags=re.I)
        t = re.sub(r'\s+\d{4}$', '', t)
        t = t.replace('-', ' ').replace(':', ' ').replace(',', ' ')
        t = re.sub(r'\s+', ' ', t).strip()
        
        return t

    @staticmethod
    def parse_filename(filename: str) -> Dict[str, Any]:
        """
        Extracts technical metadata from a filename using PTN and custom logic.
        """
        if not filename:
            return {}
            
        p = PTN.parse(filename)
        
        # Title handling
        raw_title = p.get('title', filename)
        title = html.unescape(raw_title) if raw_title else raw_title
        
        # Category detection
        category = "series" if p.get('season') is not None else "movie"
        
        # Handle lists for season/episode
        def format_seq(val):
            if isinstance(val, list):
                return ", ".join(map(str, val))
            return str(val) if val is not None else None

        # Resolution correction
        res = p.get('resolution')
        if not res and ("4KLIGHT" in filename.upper()):
            res = "4KLIGHT"

        # Language handling
        langs = p.get('language', [])
        if isinstance(langs, str): langs = [langs]
        
        fn_up = filename.upper()
        if (p.get('multi') or ".MULTI." in fn_up or " MULTI " in fn_up) and "MULTI" not in [l.upper() for l in langs]:
            langs.append("MULTI")
        if (".VOSTFR." in fn_up or " VOSTFR " in fn_up or " VOSTFR" in fn_up) and "VOST" not in [l.upper() for l in langs]:
            langs.append("VOST")

        return {
            "title": title,
            "category": category,
            "year": p.get('year'),
            "season": format_seq(p.get('season')),
            "episode": format_seq(p.get('episode')),
            "resolution": str(res) if res else None,
            "quality": p.get('quality'),
            "codec": p.get('codec'),
            "network": ParserService.clean_network_name(p.get('network')) or "",
            "v_quality": ParserService.extract_v_quality(filename) or "",
            "languages": langs
        }

parser_service = ParserService()
