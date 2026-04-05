import httpx
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from app.core.config import settings

class TMDbService:
    def __init__(self):
        self.api_key = settings.TMDB_API_KEY
        self.base_url = "https://api.themoviedb.org/3"
        self.image_url = "https://image.tmdb.org/t/p/w500"
        # Posters are stored in app/static/posters/
        self.poster_dir = Path("app/static/posters")
        self.poster_dir.mkdir(parents=True, exist_ok=True)

    async def fetch_metadata(self, title: str, year: Optional[int] = None, media_type: Optional[str] = "movie") -> Optional[Dict[str, Any]]:
        """
        Fetch movie/series metadata (Title, Plot, IMDB ID, Poster Path) from TMDb.
        Attempts to get both English and French plots.
        """
        if not self.api_key:
            return None

        try:
            print(f"[TMDB] Searching for '{title}' ({year})...")
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. Search for the media
                search_params = {
                    "api_key": self.api_key,
                    "query": title,
                    "language": "en-US"
                }
                if year:
                    search_params["year" if media_type == "movie" else "first_air_date_year"] = year

                endpoint = "search/movie" if media_type == "movie" else "search/tv"
                r = await client.get(f"{self.base_url}/{endpoint}", params=search_params)
                r.raise_for_status()
                search_data = r.json()
                
                if not search_data.get("results"):
                    # Try general search if year matching failed
                    if year:
                        del search_params["year" if media_type == "movie" else "first_air_date_year"]
                        r = await client.get(f"{self.base_url}/{endpoint}", params=search_params)
                        search_data = r.json()

                if not search_data.get("results"):
                    return None

                # Take the best match
                best_match = search_data["results"][0]
                tmdb_id = best_match["id"]

                # 2. Get full details including translations and external IDs (IMDB)
                detail_params = {
                    "api_key": self.api_key,
                    "append_to_response": "translations,external_ids"
                }
                
                detail_endpoint = "movie" if media_type == "movie" else "tv"
                r = await client.get(f"{self.base_url}/{detail_endpoint}/{tmdb_id}", params=detail_params)
                r.raise_for_status()
                details = r.json()

                imdb_id = details.get("external_ids", {}).get("imdb_id")
                
                # Extract plots
                plot_en = details.get("overview")
                plot_fr = None
                
                translations = details.get("translations", {}).get("translations", [])
                for trans in translations:
                    if trans.get("iso_639_1") == "fr":
                        plot_fr = trans.get("data", {}).get("overview")
                        break

                # If French plot is still empty, fallback to English
                if not plot_fr:
                    plot_fr = plot_en

                return {
                    "official_title": details.get("title") if media_type == "movie" else details.get("name"),
                    "year": year, # Keep original year
                    "poster_url": f"{self.image_url}{details.get('poster_path')}" if details.get('poster_path') else None,
                    "plot_en": plot_en,
                    "plot_fr": plot_fr,
                    "imdb_id": imdb_id
                }

        except Exception as e:
            print(f"[TMDB] Error fetching metadata for '{title}': {e}")
            return None

    async def download_poster(self, imdb_id: str, poster_url: str) -> Optional[str]:
        """
        Download a poster image and save it locally. (Reuse OMDb logic if needed, but here's a standalone one).
        """
        if not poster_url or not imdb_id:
            return None
        
        filename = f"{imdb_id}.jpg"
        local_path = self.poster_dir / filename
        local_url = f"static/posters/{filename}"

        if local_path.exists():
            return local_url

        try:
            print(f"[TMDB] Downloading poster: {poster_url}")
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(poster_url)
                response.raise_for_status()
                with open(local_path, "wb") as f:
                    f.write(response.content)
                return local_url
        except Exception as e:
            print(f"[TMDB] Failed to download poster for {imdb_id}: {e}")
            return None

# Singleton instance
tmdb_service = TMDbService()
