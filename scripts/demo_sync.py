import concurrent.futures
import time

# A mock function simulating a slow network request
def fetch_data(task_id):
    print(f"Task {task_id} started...")
    time.sleep(2)  # Simulates network or I/O delay
    print(f"Task {task_id} finished!")
    return f"Result {task_id}"

# --- 1. SYNCHRONOUS DEMO ---
def run_synchronous_demo():
    print("\n=== STARTING SYNCHRONOUS DEMO (One by One) ===")
    start_time = time.time()
    # Each function must fully complete before the next one starts
    res1 = fetch_data(1)
    res2 = fetch_data(2)
    res3 = fetch_data(3)
    end_time = time.time()
    print(f"Synchronous total time: {end_time - start_time:.2f} seconds")

# --- 2. THREADED ASYNCHRONOUS DEMO ---
def run_threaded_demo():
    print("\n=== STARTING THREADED ASYNCHRONOUS DEMO (Parallel) ===")
    start_time = time.time()
    # ThreadPoolExecutor launches tasks on separate background threads
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        # Submit schedules the function and returns a Future immediately (non-blocking)
        future1 = executor.submit(fetch_data, 1)
        future2 = executor.submit(fetch_data, 2)
        future3 = executor.submit(fetch_data, 3)
        # Gather results. .result() blocks only until that specific background thread finishes
        res1 = future1.result()
        res2 = future2.result()
        res3 = future3.result()
    end_time = time.time()
    print(f"Threaded total time: {end_time - start_time:.2f} seconds")

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    run_synchronous_demo()
    run_threaded_demo()
