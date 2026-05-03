import httpx
import os
import html
from pathlib import Path
from typing import Optional, Dict, Any, List
from app.core.config import settings

class TMDbService:
    def __init__(self):
        self.api_key = settings.TMDB_API_KEY
        self.base_url = "https://api.themoviedb.org/3"
        self.image_url = "https://image.tmdb.org/t/p/w500"
        
        # Posters directory (configured or fallback)
        try:
            self.poster_dir = Path(settings.POSTER_DIR)
            self.poster_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError):
            # Fallback for environments where /app is not writable (e.g. tests)
            self.poster_dir = Path("./data/posters")
            self.poster_dir.mkdir(parents=True, exist_ok=True)

    async def fetch_metadata(self, title: str, year: Optional[int] = None, media_type: Optional[str] = "movie", language: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch movie/series metadata (Title, Plot, IMDB ID, Poster Path) from TMDb.
        Attempts to get both English and French plots.
        """
        if not self.api_key or "[YOUR_KEY]" in self.api_key or "TMDB_API_KEY" in self.api_key:
            return None

        search_lang = language or settings.DEFAULT_LANGUAGE
        if len(search_lang) == 2:
            if search_lang.lower() == "en":
                search_lang = "en-US"
            else:
                search_lang = f"{search_lang}-{search_lang.upper()}"

        try:
            print(f"[TMDB] Searching for '{title}' ({year}) in {search_lang}...")
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. Search for the media
                search_params = {
                    "api_key": self.api_key,
                    "query": title,
                    "language": search_lang
                }
                if year:
                    search_params["year" if media_type == "movie" else "first_air_date_year"] = year

                endpoint = "search/movie" if media_type == "movie" else "search/tv"
                r = await client.get(f"{self.base_url}/{endpoint}", params=search_params)
                r.raise_for_status()
                search_data = r.json()
                
                if not search_data.get("results"):
                    print(f"[TMDB] No results found with year filter for '{title}'.")
                    # Try general search if year matching failed
                    if year:
                        del search_params["year" if media_type == "movie" else "first_air_date_year"]
                        r = await client.get(f"{self.base_url}/{endpoint}", params=search_params)
                        search_data = r.json()

                if not search_data.get("results"):
                    # Fallback: try the other media type if we found nothing
                    alt_media_type = "tv" if media_type == "movie" else "movie"
                    alt_endpoint = "search/movie" if alt_media_type == "movie" else "search/tv"
                    print(f"[TMDB] No results as {media_type}, trying as {alt_media_type} for '{title}'...")
                    
                    alt_params = {
                        "api_key": self.api_key,
                        "query": title,
                        "language": search_lang
                    }
                    if year:
                        alt_params["year" if alt_media_type == "movie" else "first_air_date_year"] = year
                    
                    r = await client.get(f"{self.base_url}/{alt_endpoint}", params=alt_params)
                    search_data = r.json()
                    
                    if not search_data.get("results") and year:
                        # Try general search for the alternative type too
                        del alt_params["year" if alt_media_type == "movie" else "first_air_date_year"]
                        r = await client.get(f"{self.base_url}/{alt_endpoint}", params=alt_params)
                        search_data = r.json()
                    
                    if search_data.get("results"):
                        media_type = alt_media_type # Update media_type for subsequent calls

                if not search_data.get("results"):
                    print(f"[TMDB] No results found at all for '{title}'.")
                    return None
                
                print(f"[TMDB] Found {len(search_data['results'])} results for '{title}'.")

                # Take the best match based on year if available
                best_match = None
                if year:
                    candidates = []
                    for res in search_data["results"]:
                        res_date = res.get("release_date") or res.get("first_air_date")
                        if res_date and str(year) in res_date:
                            candidates.append(res)
                    
                    if candidates:
                        # Sort by: exact title match (priority) then has poster then popularity
                        def sort_key_year(x):
                            t = (x.get("title") or x.get("name") or "").lower()
                            ot = (x.get("original_title") or x.get("original_name") or "").lower()
                            query_low = title.lower()
                            is_exact = (t == query_low or ot == query_low)
                            return (is_exact, x.get("poster_path") is not None, x.get("popularity", 0))

                        candidates.sort(key=sort_key_year, reverse=True)
                        best_match = candidates[0]
                        print(f"[TMDB] Selected best candidate among {len(candidates)} year matches: '{best_match.get('title') or best_match.get('name')}'")
                
                if not best_match and search_data["results"]:
                    # If no year or no year match, sort all results by exact title match then popularity
                    def sort_key_general(x):
                        t = (x.get("title") or x.get("name") or "").lower()
                        ot = (x.get("original_title") or x.get("original_name") or "").lower()
                        query_low = title.lower()
                        is_exact = (t == query_low or ot == query_low)
                        return (is_exact, x.get("poster_path") is not None, x.get("popularity", 0))

                    results = search_data["results"]
                    results.sort(key=sort_key_general, reverse=True)
                    best_match = results[0]
                    print(f"[TMDB] Selected best candidate by name/popularity: '{best_match.get('title') or best_match.get('name')}'")
                
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
                
                print(f"[TMDB] Found details for '{details.get('title') or details.get('name')}' (ID: {details.get('imdb_id') or details.get('external_ids', {}).get('imdb_id')})")
                print(f"[TMDB] Poster path: {details.get('poster_path')}")

                imdb_id = details.get("external_ids", {}).get("imdb_id")
                
                # Extract plots and titles
                plot_en = details.get("overview")
                plot_fr = None
                title_fr = None
                
                translations = details.get("translations", {}).get("translations", [])
                for trans in translations:
                    if trans.get("iso_639_1") == "fr":
                        plot_fr = trans.get("data", {}).get("overview")
                        title_fr = trans.get("data", {}).get("title") or trans.get("data", {}).get("name")
                        break

                # Extract official year
                res_date = details.get("release_date") or details.get("first_air_date")
                found_year = int(res_date[:4]) if res_date else year


                # Priority: original_title as the 'official' reference, title_fr for localized view
                official_title = details.get("original_title") or details.get("original_name") or details.get("title") or details.get("name")

                return {
                    "official_title": html.unescape(official_title) if official_title else None,
                    "title_fr": html.unescape(title_fr) if title_fr else None,
                    "year": found_year,
                    "poster_url": f"{self.image_url}{details.get('poster_path')}" if details.get('poster_path') else None,
                    "plot_en": plot_en,
                    "plot_fr": plot_fr,
                    "rating": str(details.get("vote_average")) if details.get("vote_average") else None,
                    "imdb_id": imdb_id
                }

        except Exception as e:
            print(f"[TMDB] Error fetching metadata for '{title}': {e}")
            return None

    async def fetch_metadata_by_tmdb_id(self, tmdb_id: int, media_type: str = "movie", language: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch metadata from TMDb using a TMDb ID.
        """
        if not self.api_key or not tmdb_id:
            return None

        search_lang = language or settings.DEFAULT_LANGUAGE
        if len(search_lang) == 2:
            search_lang = f"{search_lang}-{search_lang.upper()}"

        try:
            print(f"[TMDB] Fetching details for tmdb_id '{tmdb_id}' ({media_type}) in {search_lang}...")
            async with httpx.AsyncClient(timeout=10.0) as client:
                detail_params = {
                    "api_key": self.api_key,
                    "language": search_lang,
                    "append_to_response": "translations,external_ids"
                }
                
                detail_endpoint = "movie" if media_type == "movie" else "tv"
                r = await client.get(f"{self.base_url}/{detail_endpoint}/{tmdb_id}", params=detail_params)
                r.raise_for_status()
                details = r.json()
                
                # ... same logic as in fetch_metadata for processing details ...
                # Priority: English plot or French plot?
                plot_en = details.get("overview")
                plot_fr = None
                title_fr = None
                
                translations = details.get("translations", {}).get("translations", [])
                for trans in translations:
                    if trans.get("iso_639_1") == "fr":
                        plot_fr = trans.get("data", {}).get("overview")
                        title_fr = trans.get("data", {}).get("title") or trans.get("data", {}).get("name")
                        break

                res_date = details.get("release_date") or details.get("first_air_date")
                found_year = int(res_date[:4]) if res_date else None
                official_title = details.get("original_title") or details.get("original_name") or details.get("title") or details.get("name")

                return {
                    "official_title": html.unescape(official_title) if official_title else None,
                    "title_fr": html.unescape(title_fr) if title_fr else None,
                    "year": found_year,
                    "poster_url": f"{self.image_url}{details.get('poster_path')}" if details.get('poster_path') else None,
                    "plot_en": plot_en,
                    "plot_fr": plot_fr,
                    "rating": str(details.get("vote_average")) if details.get("vote_average") else None,
                    "imdb_id": details.get("external_ids", {}).get("imdb_id") or details.get("imdb_id")
                }

        except Exception as e:
            print(f"[TMDB] Error fetching details for tmdb_id '{tmdb_id}': {e}")
            return None

    async def fetch_metadata_by_imdb_id(self, imdb_id: str, title: Optional[str] = None, year: Optional[int] = None, language: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Fetch metadata from TMDb using an IMDB ID.
        Uses the /find endpoint, with fallback to title search.
        """
        if not self.api_key:
            return None

        try:
            if imdb_id:
                print(f"[TMDB] Finding metadata for IMDB ID '{imdb_id}'...")
                async with httpx.AsyncClient(timeout=10.0) as client:
                    params = {
                        "api_key": self.api_key,
                        "external_source": "imdb_id"
                    }
                    r = await client.get(f"{self.base_url}/find/{imdb_id}", params=params)
                    r.raise_for_status()
                    data = r.json()

                    # Find result in movie_results or tv_results
                    results = data.get("movie_results", []) + data.get("tv_results", [])
                    if results:
                        best_match = results[0]
                        media_type = "movie" if best_match in data.get("movie_results", []) else "tv"
                        
                        # Fetch full details
                        return await self.fetch_metadata(
                            title=best_match.get("title") or best_match.get("name"),
                            year=year,
                            media_type=media_type,
                            language=language
                        )

            # Fallback to title search if ID failed or not provided
            if title:
                print(f"[TMDB] IMDB ID lookup failed, falling back to title search for '{title}'...")
                return await self.fetch_metadata(title=title, year=year, language=language)

            return None
        except Exception as e:
            print(f"[TMDB] Error finding metadata by IMDB ID '{imdb_id}': {e}")
            return None

    async def download_poster(self, imdb_id: str, poster_url: str) -> Optional[str]:
        """
        Download a poster image and save it locally.
        """
        if not poster_url or not imdb_id:
            return None
        
        filename = f"{imdb_id}.jpg"
        local_path = self.poster_dir / filename
        local_url = f"posters/{filename}"

        if local_path.exists() and local_path.stat().st_size > 0:
            print(f"[TMDB] Poster already exists at {local_path}, skipping download.")
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
