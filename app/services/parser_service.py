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
            return ""
            
        # 1. Remove bracketed content [TAG] often found in RSS
        t = re.sub(r'\[[^\]]+\]', ' ', title)
        
        # 2. Initial normalization
        t = t.replace('.', ' ').replace('_', ' ')
        
        # 3. Remove Volume/Part markers
        t = re.sub(r'\b(Vol|Pt|Part|Partie)[\.\s]?\d+\b', ' ', t, flags=re.I)
        t = re.sub(r'\b\d+(?:e|ème|re|nd|rd|th)?\s+partie\b', ' ', t, flags=re.I)
        
        # 4. Use PTN to identify year
        p = PTN.parse(title)
        year = p.get('year')
        if year:
            t = re.sub(rf'\b{year}\b', ' ', t)
            
        # 5. Remove common technical noise
        noise = [
            r'\d{3,4}p', r'\d{1}k', r'H[\.\s]?26[45]', r'x[\.\s]?26[45]', 
            'WEB-DL', 'WEBRip', 'BluRay', 'BDRip', 'DVDRip', 'REPACK', 'PROPER', 'FINAL',
            'MULTI', 'FRENCH', 'TRUEFRENCH', 'VOSTFR', 'SUBFRENCH', 'VFF', 'VFI', 'VFQ',
            'UHD', 'DV', 'HDR', 'HEVC', r'DDP\d[\.\s]?\d', 'Atmos', 'AC3', 'DTS', 'INTERNAL', 'CUSTOM'
        ]
        for n in noise:
            t = re.sub(rf'\b{n}\b', ' ', t, flags=re.I)
            
        # 6. Normalize spaces BEFORE splitting on group separators
        t = re.sub(r'\s+', ' ', t).strip()

        # 7. Remove everything after common separators (often titles end with " - GROUP")
        t = re.split(r' \- | \– ', t)[0]
            
        # 8. Final cleanup
        t = t.strip()
        t = re.sub(r'[, \-–]+$', '', t)
        
        if len(t) < 2 and p.get('title'):
            return p.get('title').strip()
            
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
        
        # Aggressive title cleaning if tags leaked into it
        if title:
            title = re.split(r'[\.\[\s\-](?:MULTI|FRENCH|TRUEFRENCH|1080P|720P|2160P|BLURAY|UHD|VOSTFR|VFF|VFI|VFQ|DV|HDR|REPACK|PROPER|FINAL)\b', title, flags=re.I)[0]
            title = title.replace('.', ' ').strip()
        
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

        # Language & French Tags handling
        langs = p.get('language', [])
        if isinstance(langs, str): langs = [langs]
        
        fn_up = filename.upper().replace('[', '.').replace(']', '.').replace('_', '.')
        
        # Manual detection for common FR scene tags
        if "TRUEFRENCH" in fn_up or "VFF" in fn_up:
            if "FRENCH" not in [l.upper() for l in langs]: langs.append("FRENCH")
        if "MULTI" in fn_up or p.get('multi'):
            if "MULTI" not in [l.upper() for l in langs]: langs.append("MULTI")
        if "VOSTFR" in fn_up or "VOST" in fn_up:
            if "VOSTFR" not in [l.upper() for l in langs]: langs.append("VOSTFR")
        if "VFI" in fn_up or "VFQ" in fn_up:
            if "VF" not in [l.upper() for l in langs]: langs.append("VF")

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
