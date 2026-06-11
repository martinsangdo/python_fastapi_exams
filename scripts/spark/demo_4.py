import os
import sys
import requests

# 1. Force the underlying Java process to ignore the missing incubator vector module
os.environ["JAVA_HOME"] = "/opt/homebrew/opt/openjdk@17"
os.environ["PYSPARK_PYTHON"] = "/opt/homebrew/bin/python3.10"
os.environ["PYSPARK_DRIVER_PYTHON"] = "/opt/homebrew/bin/python3.10"

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, explode
from pyspark.sql.types import IntegerType, DoubleType

print("--- 📥 STEP 1: DEFENSIVE API INGESTION ---")
url = "https://dummyjson.com/carts"

try:
    response = requests.get(url, timeout=10)
    
    # Check if the website returned a 200 OK status code
    response.raise_for_status() 
    
    # Catch situations where response body is empty or plain text
    api_data = response.json()
    print("Successfully downloaded API data payload.")

except requests.exceptions.HTTPError as http_err:
    print(f"❌ Server HTTP Error: {http_err}")
    print(f"Response text received:\n{response.text[:300]}")
    sys.exit(1)
except requests.exceptions.JSONDecodeError:
    print("❌ Critical Error: The server responded, but it was NOT valid JSON text.")
    print(f"Raw response content string:\n{response.text[:500]}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Connection or Timeout Error: {e}")
    sys.exit(1)

print("\n--- ⚡ STEP 2: SPINNING UP LOCAL SPARK CLUSTER ---")
spark = SparkSession.builder \
    .appName("APICalculationDemo") \
    .master("local[*]") \
    .getOrCreate()

# Load the verified data array
raw_carts_df = spark.createDataFrame(api_data["carts"])

print("\n--- 🧹 STEP 3: FLATTENING & EXPLICIT TYPING ---")
# Because Spark inferred the inner fields as a Map, we pull keys explicitly
flattened_products_df = raw_carts_df \
    .select(explode(col("products")).alias("product_item")) \
    .select(
        col("product_item")["id"].alias("product_id"),
        col("product_item")["title"].alias("product_title"),
        col("product_item")["quantity"].cast(IntegerType()).alias("qty"),
        col("product_item")["price"].cast(DoubleType()).alias("unit_price")
    )

print("\n--- 📊 STEP 4: CALCULATING PRODUCT REVENUE ---")
product_revenue_df = flattened_products_df \
    .withColumn("item_revenue", col("qty") * col("unit_price")) \
    .groupBy("product_id", "product_title") \
    .sum("item_revenue") \
    .withColumnRenamed("sum(item_revenue)", "total_product_revenue") \
    .orderBy(col("total_product_revenue").desc())

print("--- 🎉 PRODUCTION CALCULATION LOG OUTPUT ---")
product_revenue_df.show(10, truncate=False)

spark.stop()
