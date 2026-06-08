import asyncio
import random
import time

# --- 1. SYNCHRONOUS (BLOCKING) DEMO ---
def fetch_data_sync(task_id):
    print(f"[Sync] Task {task_id} started...")
    # This blocks the entire thread. Nothing else can happen.
    time.sleep(random.randint(1, 3))  
    print(f"[Sync] Task {task_id} finished!")
    return f"Result {task_id}"

def run_synchronous_demo():
    print("\n=== STARTING SYNCHRONOUS DEMO ===")
    start_time = time.time()
    
    # Tasks run strictly one after the other
    res1 = fetch_data_sync(1)
    res2 = fetch_data_sync(2)
    res3 = fetch_data_sync(3)
    
    end_time = time.time()
    print(f"Synchronous total execution time: {end_time - start_time:.2f} seconds")


# --- 2. ASYNCHRONOUS (NON-BLOCKING) DEMO ---
async def fetch_data_async(task_id):
    print(f"[Async] Task {task_id} started...")
    # This pauses the task, yielding control back to the event loop
    await asyncio.sleep(2)  
    print(f"[Async] Task {task_id} finished!")
    return f"Result {task_id}"

async def run_asynchronous_demo():
    print("\n=== STARTING ASYNCHRONOUS DEMO ===")
    start_time = time.time()
    
    # Schedule all three tasks to run concurrently
    results = await asyncio.gather(
        fetch_data_async(1),
        fetch_data_async(2),
        fetch_data_async(3)
    )
    
    end_time = time.time()
    print(f"Asynchronous total execution time: {end_time - start_time:.2f} seconds")


# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # Run the blocking code
    run_synchronous_demo()
    
    # Run the non-blocking code using the asyncio event loop
    asyncio.run(run_asynchronous_demo())
