import httpx
import os
from pathlib import Path
from typing import Optional, Dict, Any
from app.core.config import settings

class OMDbService:
    def __init__(self):
        self.api_key = settings.OMDB_API_KEY
        self.base_url = "http://www.omdbapi.com/"
        # Posters are stored in app/static/posters/
        self.poster_dir = Path("app/static/posters")
        self.poster_dir.mkdir(parents=True, exist_ok=True)

    async def download_poster(self, imdb_id: str, poster_url: str) -> Optional[str]:
        """
        Download a poster image and save it locally.
        Returns the local static path (starting with static/posters/).
        """
        if not poster_url or poster_url == "N/A" or not imdb_id:
            return None
        
        # Determine extension (default to jpg if unclear)
        file_ext = poster_url.split('.')[-1].split('?')[0].lower()
        if file_ext not in ["jpg", "jpeg", "png", "webp"]:
            file_ext = "jpg"
        
        filename = f"{imdb_id}.{file_ext}"
        local_path = self.poster_dir / filename
        # This is the path used in the frontend (relative to static mount)
        local_url = f"static/posters/{filename}"

        if local_path.exists():
            return local_url

        try:
            print(f"[OMDB] Downloading poster: {poster_url}")
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(poster_url)
                response.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(response.content)
                return local_url
        except Exception as e:
            print(f"[OMDB] Failed to download poster for {imdb_id}: {e}")
            return None

    async def fetch_metadata(self, title: str, year: Optional[int] = None, media_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch movie/series metadata (Title, Plot, IMDB ID, Poster URL) from OMDb.
        """
        if not self.api_key:
            return None

        params = {
            "apikey": self.api_key,
            "t": title,
            "plot": "short"
        }
        if year:
            params["y"] = str(year)
        if media_type:
            params["type"] = media_type

        try:
            print(f"[OMDB] Fetching metadata for '{title}'...")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()
                print(f"[OMDB] Metadata for '{title}': {data}")
                if data.get("Response") == "True":
                    return self._process_omdb_data(data)
                
                # Fallback: Search by s= (search) if t= (exact title) fails
                print(f"[OMDB] Exact match failed for '{title}', trying general search...")
                search_params = {
                    "apikey": self.api_key,
                    "s": title,
                }
                if media_type:
                    search_params["type"] = media_type
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    s_response = await client.get(self.base_url, params=search_params)
                    s_data = s_response.json()
                    
                    if s_data.get("Response") == "True":
                        results = s_data.get("Search", [])
                        best_match_id = None
                        
                        # Try to find a match with the correct year
                        if year:
                            for res in results:
                                if str(year) in res.get("Year", ""):
                                    best_match_id = res.get("imdbID")
                                    break
                        
                        # Fallback to first result if no year match
                        if not best_match_id and results:
                            best_match_id = results[0].get("imdbID")
                            
                        if best_match_id:
                            # Fetch full metadata using the found IMDB ID
                            print(f"[OMDB] Found potential match via search: {best_match_id}")
                            id_params = {"apikey": self.api_key, "i": best_match_id, "plot": "short"}
                            id_response = await client.get(self.base_url, params=id_params)
                            return self._process_omdb_data(id_response.json())

                return None
        except Exception as e:
            print(f"[OMDB] Error fetching metadata for '{title}': {e}")
            return None

    def _process_omdb_data(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Helper to parse OMDb API response."""
        if not data or data.get("Response") != "True":
            return None
            
        raw_year = data.get("Year")
        parsed_year = None
        if raw_year:
            import re
            match = re.search(r'\d{4}', raw_year)
            if match:
                parsed_year = int(match.group())

        return {
            "official_title": data.get("Title"),
            "year": parsed_year,
            "poster_url": data.get("Poster"),
            "plot": data.get("Plot") if data.get("Plot") != "N/A" else None,
            "imdb_id": data.get("imdbID")
        }

# Singleton instance
omdb_service = OMDbService()
