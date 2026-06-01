import aiohttp
import re
from typing import Optional, Dict, Any
from app.core.utils import parse_size


class DailyUploadsService:
    """
    Direct HTTP verification for dailyuploads.net (XFileSharing platform).

    Strategy:
    - GET  → check alive/dead + extract exact filename from hidden input name="fname"
    - POST → submit the free-download form (op=download1) to retrieve the file size in bytes
    """
    @staticmethod
    async def check(url: str, session: Optional[aiohttp.ClientSession] = None) -> Dict[str, Any]:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        if session:
            return await DailyUploadsService._do_check(url, session, headers)
        else:
            async with aiohttp.ClientSession(headers=headers) as new_session:
                return await DailyUploadsService._do_check(url, new_session, {})

    @staticmethod
    async def _do_check(url: str, session: aiohttp.ClientSession, headers: Dict[str, str]) -> Dict[str, Any]:
        try:
            # --- Step 1: GET — check alive/dead and extract filename + file id ---
            async with session.get(url, allow_redirects=True, timeout=aiohttp.ClientTimeout(total=15), headers=headers) as response:
                if response.status == 404:
                    return {"status": "dead", "host": "dailyuploads.net"}

                if response.status != 200:
                    return {"status": "unknown", "host": "dailyuploads.net"}

                html = await response.text(errors="replace")

            if "file not found" in html.lower():
                return {"status": "dead", "host": "dailyuploads.net"}

            # Extract filename from hidden input name="fname" (exact name with dots & extension)
            fname_match = re.search(
                r'<input[^>]+name=["\']fname["\'][^>]+value=["\']([^"\']+)["\']',
                html, re.IGNORECASE
            ) or re.search(
                r'<input[^>]+value=["\']([^"\']+)["\'][^>]+name=["\']fname["\']',
                html, re.IGNORECASE
            )

            # Fallback: <title>Download <filename></title>
            title_match = re.search(r"<title>\s*Download\s+(.+?)\s*</title>", html, re.IGNORECASE)

            name = ""
            if fname_match:
                name = fname_match.group(1).strip()
            elif title_match:
                name = title_match.group(1).strip()

            if not name:
                return {"status": "unknown", "host": "dailyuploads.net"}

            # Extract file id from URL or hidden input name="id"
            file_id_match = re.search(r'name=["\']id["\'][^>]+value=["\']([^"\']+)["\']', html, re.IGNORECASE)
            file_id = file_id_match.group(1).strip() if file_id_match else url.rstrip("/").split("/")[-1]

            # --- Step 2: POST — submit free-download form to get file size ---
            size_bytes = 0
            try:
                post_data = {
                    "op": "download1",
                    "usr_login": "",
                    "id": file_id,
                    "fname": name,
                    "referer": "",
                    "method_free": "Free Download",
                }
                async with session.post(url, data=post_data, allow_redirects=True,
                                        timeout=aiohttp.ClientTimeout(total=15), headers=headers) as post_resp:
                    if post_resp.status == 200:
                        post_html = await post_resp.text(errors="replace")

                        # Prefer exact bytes: "(1972720608 bytes)"
                        bytes_match = re.search(r"\((\d+)\s*bytes\)", post_html, re.IGNORECASE)
                        if bytes_match:
                            size_bytes = int(bytes_match.group(1))
                        else:
                            # Fallback: human-readable size like "1.8 GB"
                            size_match = re.search(r"(\d+(?:[.,]\d+)?\s*(?:GB|MB|KB))\b", post_html, re.IGNORECASE)
                            if size_match:
                                size_bytes = parse_size(size_match.group(1).strip())
            except Exception:
                pass  # Size is optional — don't fail the whole check

            return {
                "status": "alive",
                "filename": name,
                "size": size_bytes,
                "host": "dailyuploads.net",
            }

        except Exception as e:
            return {"status": "error", "host": "dailyuploads.net", "error": str(e)}
