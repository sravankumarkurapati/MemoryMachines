import asyncio
import aiohttp
import time

API_URL = "https://log-processor-api-267365813208.us-east1.run.app/ingest"

async def send_request(session, i):
    try:
        payload = {
            "tenant_id": f"tenant_{i % 10}",
            "log_id": f"test_{i}",
            "text": f"Test {i}"
        }
        
        async with session.post(API_URL, json=payload) as response:
            status = response.status
            text = await response.text()
            return {"status": status, "response": text[:200]}
    except Exception as e:
        return {"status": "error", "error": str(e)}

async def main():
    async with aiohttp.ClientSession() as session:
        # Send just 5 requests to debug
        tasks = [send_request(session, i) for i in range(5)]
        results = await asyncio.gather(*tasks)
        
        for i, result in enumerate(results):
            print(f"\nRequest {i}:")
            print(f"  Status: {result.get('status')}")
            if 'error' in result:
                print(f"  Error: {result['error']}")
            if 'response' in result:
                print(f"  Response: {result['response']}")

asyncio.run(main())
