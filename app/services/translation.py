import httpx
from typing import Optional
from app.core.config import settings

class TranslationService:
    def __init__(self):
        self.base_url = "https://api.mymemory.translated.net/get"
        self.email = settings.MYMEMORY_EMAIL

    async def translate(self, text: str, from_lang: str = "en", to_lang: str = "fr") -> Optional[str]:
        """
        Translate text using the MyMemory API.
        """
        if not text or text == "N/A":
            return None
            
        params = {
            "q": text,
            "langpair": f"{from_lang}|{to_lang}",
            "de": self.email
        }
        
        try:
            print(f"[TRANSLATION] Translating to {to_lang}...")
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.base_url, params=params)
                response.raise_for_status()
                data = response.json()
                
                status_code = data.get("responseStatus")
                if status_code == 200:
                    translated = data.get("responseData", {}).get("translatedText")
                    if translated:
                        # MyMemory sometimes returns HTML entities
                        import html
                        return html.unescape(translated)
                
                print(f"[TRANSLATION] API returned status {status_code}: {data.get('responseDetails')}")
                return None
        except Exception as e:
            print(f"[TRANSLATION] Error translating: {e}")
            return None

# Singleton instance
translation_service = TranslationService()
