import asyncio
import sys
import os

# Ensure the app directory is in the path
sys.path.append(os.getcwd())

try:
    from app.core.config import settings
    from app.services.debrid import debrid_service
    from app.services.alldebrid import AllDebridClient
    from app.services.realdebrid import RealDebridClient
except ImportError as e:
    print(f"Error: Could not import app modules. Are you running this from the project root? ({e})")
    sys.exit(1)

async def test_debrid_setup():
    print("=" * 50)
    print("DDL TOWER - DEBRID SERVICE VERIFICATION")
    print("=" * 50)

    # 1. Config Check
    print(f"\n[1] Configuration Check:")
    ad_key = settings.ALLDEBRID_API_KEY
    rd_key = settings.REALDEBRID_API_KEY
    bd_key = settings.BESTDEBRID_API_KEY
    
    print(f"  - AllDebrid API Key: {'Set' if ad_key and ad_key != '[YOUR_KEY]' else 'Not set/Default'}")
    print(f"  - Real-Debrid API Key: {'Set' if rd_key and rd_key != '[YOUR_KEY]' else 'Not set/Default'}")
    print(f"  - BestDebrid API Key: {'Set' if bd_key and bd_key != '[YOUR_KEY]' else 'Not set/Default'}")

    # 2. Service Selection
    print(f"\n[2] Service Selection:")
    client = debrid_service.get_client()
    print(f"  - Currently active client: {type(client).__name__}")

    # 3. Functional Test (Mocked or Real if keys are set)
    test_link = "https://rapidgator.net/file/bbdc2c55e031ec067eb05a30142d94aa/DaDai22326pWEBLDD526SIKL.part1.rar.html"
    print(f"\n[3] Functional Check (Checking link: {test_link}):")
    
    try:
        results = await client.check_links([test_link])
        if test_link in results:
            info = results[test_link]
            print(f"  - Link status: {info.get('status', 'Unknown')}")
            if info.get('error'):
                print(f"  - API Error: {info.get('error')}")
            else:
                print(f"  - Link info: Host={info.get('host')}, Size={info.get('size')}")
                
                # Try to unlock if it's alive
                if info.get('status') == 'alive':
                    print(f"\n[4] Unlock Test:")
                    unlock_res = await client.unlock_link(test_link)
                    if unlock_res.get('status') == 'success':
                        print(f"  - Unlock Success!")
                        print(f"  - Filename: {unlock_res.get('data', {}).get('filename')}")
                        print(f"  - Download Link: {unlock_res.get('data', {}).get('link')[:50]}...")
                    else:
                        print(f"  - Unlock Failed: {unlock_res.get('error')}")
        else:
            print("  - No results returned for the test link.")
    except Exception as e:
        print(f"  - Error during check: {str(e)}")

    print("\n" + "=" * 50)
    print("Verification complete.")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(test_debrid_setup())
