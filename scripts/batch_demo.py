import time

# 1. Bounded Data (A fixed collection of records)
sales_batch = [
    {"item": "Laptop", "price": 1200},
    {"item": "Mouse", "price": 25},
    {"item": "Keyboard", "price": 75},
    {"item": "Monitor", "price": 300},
    {"item": "HDMI Cable", "price": 15}
]

print("--- STARTING BATCH JOB ---")
time.sleep(1.5)  # Simulating processing delay
total_revenue = sum(sale["price"] for sale in sales_batch)
print("--- END OF BATCH JOB --- with total revenue:\n", total_revenue)