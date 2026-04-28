from app.core.scheduler import run_scrapers

class ScanCommands:
    @staticmethod
    async def trigger(source_name: str = None):
        if source_name:
            print(f"--- [SCAN] Starting manual scan for: {source_name} ---")
        else:
            print("--- [SCAN] Starting manual full scan ---")
            
        try:
            await run_scrapers(source_name=source_name)
            print("--- [SCAN] Manual scan finished ---")
        except Exception as e:
            print(f"[SCAN] Error during manual scan: {e}")
