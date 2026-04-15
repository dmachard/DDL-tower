from app.core.scheduler import run_scrapers

class ScanCommands:
    @staticmethod
    async def trigger():
        print("--- [SCAN] Starting manual full scan ---")
        try:
            await run_scrapers()
            print("--- [SCAN] Manual scan finished ---")
        except Exception as e:
            print(f"[SCAN] Error during manual scan: {e}")
