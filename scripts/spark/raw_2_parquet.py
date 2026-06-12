import json
import os
import pandas as pd
# ----------------------------------------------------
# 1. CREATE MOCK RAW DATA (Simulation)
# ----------------------------------------------------
raw_json_data = [
    {"user_id": 101, "review_text": "Great product! Highly recommend.", "rating": 5, "signup_date": "2023-01-15"},
    {"user_id": 102, "review_text": "It was okay, but arrived late.", "rating": 3, "signup_date": "2023-02-20"},
    {"user_id": 103, "review_text": "Broken on arrival. Terrible.", "rating": 1, "signup_date": "2023-01-15"},
    {"user_id": 104, "review_text": "", "rating": None, "signup_date": "2023-03-05"},
]
with open("raw_interactions.json", "w") as f:
    json.dump(raw_json_data, f)
print("✅ Step 1: Raw JSON dataset created.")
# ----------------------------------------------------
# 2. INGEST & CLEAN DATA FOR AI
# ----------------------------------------------------
# Load the raw data into memory
df = pd.read_json("raw_interactions.json")

# AI Clean 1: Handle missing values (AI models cannot handle NaN values)
df["review_text"] = df["review_text"].fillna("No review provided")
df["rating"] = df["rating"].fillna(df["rating"].median())  # Impute missing ratings

# AI Clean 2: Cast explicitly to efficient, strict data types
df["user_id"] = df["user_id"].astype("int64")
df["review_text"] = df["review_text"].astype("string")
df["rating"] = df["rating"].astype("float32")  # Float32 uses less VRAM during AI training
df["signup_date"] = pd.to_datetime(df["signup_date"])

print("✅ Step 2: Data cleaned and tokenization-ready types applied.")

# ----------------------------------------------------
# 3. CONVERT AND SAVE TO PARQUET
# ----------------------------------------------------
# Define output directory
output_dir = "ai_training_lake.parquet"

# Write to Parquet, partitioned by date to allow fast chunked-loading during training
df.to_parquet(
    output_dir,
    engine="pyarrow",
    compression="snappy",
    # partition_cols=["signup_date"],   #this will create subfolders for each unique signup_date, which is ideal for large datasets but may be overkill for this small example
    index=False
)

print(f"✅ Step 3: Raw data compiled and saved into Parquet format at: '{output_dir}/'")

# ----------------------------------------------------
# 4. VERIFY THE PARQUET DIRECTORY STRUCTURE
# ----------------------------------------------------
print("\n--- Inspecting the Generated Data Lake Folder ---")
for root, dirs, files in os.walk(output_dir):
    for file in files:
        print(os.path.join(root, file))
