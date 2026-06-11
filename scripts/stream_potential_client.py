import time
import random
def live_shopper_stream():
    username_prefix = "user "
    while True:
        yield {
            "user": f"{username_prefix}{random.randint(1, 100)}",
            "cart_value": random.randint(10, 600)
        }
        time.sleep(random.uniform(0.6, 1.2))
print("--- STARTING STREAMING ENGINE (Press Ctrl+C to Stop) ---\n")
for customer in live_shopper_stream():
    user = customer["user"]
    value = customer["cart_value"]
    if value > 500:
        status_flag = "🔥 [HIGH POTENTIAL CLIENT DETECTED]"
    else:
        status_flag = "   [Standard Shopper]"
    print(f"[STREAM] User: {user:<7} | Cart: ${value:<4} | {status_flag}")
# This script simulates a live stream of shoppers adding items to their carts, with a focus on identifying high potential clients based on cart value.