import asyncio
from typing import Dict, Any

class YoutubeService:
    """
    Direct verification for YouTube URLs using yt-dlp.
    """
    @staticmethod
    async def check(url: str, session: Any = None) -> Dict[str, Any]:
        try:
            import yt_dlp
            print(f"[YOUTUBE] Verifying link: {url}")
            
            # Options to just extract title/info without downloading
            ydl_opts = {
                'format': 'best',
                'quiet': True,
                'no_warnings': True,
            }
            
            loop = asyncio.get_event_loop()
            def extract():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, extract)
            title = info.get('title')
            ext = info.get('ext', 'mp4')
            
            if title:
                # Clean up filename (replace slashes to avoid directory traversal)
                filename = f"{title}.{ext}".replace("/", "_")
                return {
                    "status": "alive",
                    "filename": filename,
                    "size": 0,
                    "host": "youtube.com"
                }
            
            return {"status": "unknown", "host": "youtube.com"}
        except Exception as e:
            print(f"[YOUTUBE] Verification failed for {url}: {e}")
            return {"status": "error", "host": "youtube.com", "error": str(e)}
