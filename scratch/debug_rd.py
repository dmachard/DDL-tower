import aiohttp
import asyncio

async def debug_rd():
    base_url = "https://api.real-debrid.com/rest/1.0"
    token = "RBWCKDLRXDHFEQK6KJBCGUMHHROYBTVO3JZP3SBPH4B3A7RKZNRA"
    test_link = "https://rapidgator.net/file/bbdc2c55e031ec067eb05a30142d94aa/DaDai22326pWEBLDD526SIKL.part1.rar.html"
    
    async with aiohttp.ClientSession() as session:
        # Test 1: POST with data
        print("Test 1: POST /unrestrict/check with data")
        async with session.post(f"{base_url}/unrestrict/check", data={"link": test_link}) as resp:
            print(f"Status: {resp.status}")
            print(f"Body: {await resp.text()}")

        # Test 2: POST with params
        print("\nTest 2: POST /unrestrict/check with params")
        async with session.post(f"{base_url}/unrestrict/check", params={"link": test_link}) as resp:
            print(f"Status: {resp.status}")
            print(f"Body: {await resp.text()}")

        # Test 3: GET with params
        print("\nTest 3: GET /unrestrict/check with params")
        async with session.get(f"{base_url}/unrestrict/check", params={"link": test_link}) as resp:
            print(f"Status: {resp.status}")
            print(f"Body: {await resp.text()}")

        # Test 4: Verify Auth with /user
        print("\nTest 4: GET /user with Auth")
        headers = {"Authorization": f"Bearer {token}"}
        async with session.get(f"{base_url}/user", headers=headers) as resp:
            print(f"Status: {resp.status}")
            print(f"Body: {await resp.text()}")

if __name__ == "__main__":
    asyncio.run(debug_rd())
