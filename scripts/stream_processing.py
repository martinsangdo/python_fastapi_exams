import time
import random

# 1. Unbounded Data Generator (Simulates a continuous stream)
def live_click_stream():
    click_id = 1
    while True:
        # Simulate a user clicking home, product, or checkout pages
        yield {"click_id": click_id, "page": random.choice(["Home", "Product", "Checkout"])}
        click_id += 1
        time.sleep(random.uniform(0.5, 1.5))  # Random arrival time
print("--- STARTING STREAMING ENGINE (Press Ctrl+C to Stop) ---")
running_click_count = 0
# 2. Process data point-by-point as it arrives
for click in live_click_stream():
    running_click_count += 1
    # Live transformation / filtering logic
    if click["page"] == "Checkout":
        alert = "⚠️ high priority event!"
    else:
        alert = ""
    # 3. Output live, real-time updates
    print(f"[STREAM] New Event -> ID: {click['click_id']} | Page: {click['page']:<8} | Total Clicks Tracked: {running_click_count} {alert}")
