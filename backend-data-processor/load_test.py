"""
Load testing script - Simulates company's chaos test.
Sends 1,000 requests per minute with mixed JSON and text formats.
"""
import asyncio
import aiohttp
import time
from datetime import datetime

API_URL = "https://log-processor-api-267365813208.us-east1.run.app/ingest"

async def send_json_request(session, i):
    """Send JSON format request."""
    try:
        payload = {
            "tenant_id": f"tenant_{i % 10}",  # 10 different tenants
            "log_id": f"load_test_{i}",
            "text": f"Load test message {i} with email test{i}@example.com and phone 555-{i:04d}"
        }
        
        async with session.post(
            API_URL,
            json=payload,
            headers={"Content-Type": "application/json"}
        ) as response:
            status = response.status
            return {"index": i, "format": "json", "status": status}
    except Exception as e:
        return {"index": i, "format": "json", "status": "error", "error": str(e)}


async def send_text_request(session, i):
    """Send plain text format request."""
    try:
        text = f"Load test message {i} from tenant_{i % 10}"
        
        async with session.post(
            API_URL,
            data=text,
            headers={
                "Content-Type": "text/plain",
                "X-Tenant-ID": f"tenant_{i % 10}"
            }
        ) as response:
            status = response.status
            return {"index": i, "format": "text", "status": status}
    except Exception as e:
        return {"index": i, "format": "text", "status": "error", "error": str(e)}


async def load_test(total_requests=1000, concurrent=50):
    """
    Run load test.
    
    Args:
        total_requests: Total number of requests to send
        concurrent: Number of concurrent requests
    """
    print(f"\n{'='*60}")
    print(f"LOAD TEST STARTING")
    print(f"{'='*60}")
    print(f"Target: {total_requests} requests")
    print(f"Concurrency: {concurrent} requests at a time")
    print(f"API URL: {API_URL}")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    start_time = time.time()
    results = []
    
    # Create connector with connection pooling
    connector = aiohttp.TCPConnector(limit=concurrent, limit_per_host=concurrent)
    timeout = aiohttp.ClientTimeout(total=30)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = []
        
        for i in range(total_requests):
            # Alternate between JSON and text formats
            if i % 2 == 0:
                task = send_json_request(session, i)
            else:
                task = send_text_request(session, i)
            
            tasks.append(task)
            
            # Process in batches to control concurrency
            if len(tasks) >= concurrent:
                batch_results = await asyncio.gather(*tasks)
                results.extend(batch_results)
                tasks = []
                
                # Progress update
                if len(results) % 100 == 0:
                    print(f"Progress: {len(results)}/{total_requests} requests sent...")
        
        # Process remaining tasks
        if tasks:
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
    
    end_time = time.time()
    elapsed = end_time - start_time
    
    # Analyze results
    total = len(results)
    success_202 = sum(1 for r in results if r.get("status") == 202)
    errors = sum(1 for r in results if r.get("status") == "error")
    other_status = total - success_202 - errors
    
    success_rate = (success_202 / total * 100) if total > 0 else 0
    rps = total / elapsed if elapsed > 0 else 0
    
    # Print results
    print(f"\n{'='*60}")
    print(f"LOAD TEST RESULTS")
    print(f"{'='*60}")
    print(f"Total Requests:      {total}")
    print(f"Successful (202):    {success_202} ({success_rate:.2f}%)")
    print(f"Errors:              {errors}")
    print(f"Other Status:        {other_status}")
    print(f"{'='*60}")
    print(f"Time Elapsed:        {elapsed:.2f} seconds")
    print(f"Requests/Second:     {rps:.2f} RPS")
    print(f"Avg Response Time:   {(elapsed/total*1000):.2f} ms")
    print(f"{'='*60}")
    
    # Pass/Fail criteria
    print(f"\n{'='*60}")
    print(f"PASS/FAIL CRITERIA")
    print(f"{'='*60}")
    
    pass_criteria = {
        "Success Rate > 95%": success_rate > 95,
        "RPS > 15": rps > 15,
        "Total Errors < 50": errors < 50
    }
    
    all_passed = all(pass_criteria.values())
    
    for criteria, passed in pass_criteria.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{criteria:<30} {status}")
    
    print(f"{'='*60}")
    print(f"\nOVERALL: {'✅ PASSED' if all_passed else '❌ FAILED'}")
    print(f"{'='*60}\n")
    
    return results, all_passed


if __name__ == "__main__":
    # Run the load test
    results, passed = asyncio.run(load_test(total_requests=1000, concurrent=50))
    
    # Exit with appropriate code
    exit(0 if passed else 1)
