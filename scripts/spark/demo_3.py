import os
import time
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType
from pyspark.sql.functions import col, expr

# 1. Set up a local folder to simulate an active streaming source
source_dir = "./stream_input_source"
os.makedirs(source_dir, exist_ok=True)

spark = SparkSession.builder \
    .appName("AdvancedStreamingDemo") \
    .master("local[*]") \
    .getOrCreate()

# 2. Define the explicit schema for incoming data stream
schema = StructType([
    StructField("user", StringType(), True),
    StructField("cart_value", IntegerType(), True)
])

# 3. Read stream from the directory (Spark watches this folder for new files)
streaming_df = spark.readStream \
    .schema(schema) \
    .json(source_dir)

# 4. Apply streaming transformation logic
processed_stream = streaming_df.withColumn(
    "status", 
    expr("CASE WHEN cart_value > 500 THEN '🔥 HIGH POTENTIAL' ELSE 'Standard' END")
)

# 5. Write stream result to terminal console
query = processed_stream.writeStream \
    .outputMode("append") \
    .format("console") \
    .start()

print(f"--- STREAMING ACTIVE: Drop JSON files into '{source_dir}' directory ---")
print("Simulating a live event drop now...")

# Mock Helper: Simulates an external application dropping a file into the directory
time.sleep(3)
mock_json_payload = '{"user": "Emma", "cart_value": 1200}\n{"user": "James", "cart_value": 250}'
with open(f"{source_dir}/batch_1.json", "w") as f:
    f.write(mock_json_payload)

# Keep the streaming query active for 15 seconds to observe console updates
time.sleep(15)
query.stop()
spark.stop()
