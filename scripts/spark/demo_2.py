from pyspark.sql import SparkSession
from pyspark.sql.functions import col

spark = SparkSession.builder \
    .appName("IntermediateETLDemo") \
    .master("local[*]") \
    .getOrCreate()

# 1. Mock Raw Data Sources
users_data = [("1", "Alice"), ("2", "Bob"), ("3", "Charlie"), ("4", "David")]
purchases_data = [("1", 1200), ("2", 450), ("3", 80), ("4", 1500), ("1", 300)]

users_df = spark.createDataFrame(users_data, ["user_id", "name"])
purchases_df = spark.createDataFrame(purchases_data, ["user_id", "cart_value"])

# 2. Transformation: Join datasets, aggregate total spend, and filter
analytics_df = users_df.join(purchases_df, "user_id", "inner") \
    .groupBy("user_id", "name") \
    .sum("cart_value") \
    .withColumnRenamed("sum(cart_value)", "total_spend") \
    .filter(col("total_spend") > 500) \
    .orderBy(col("total_spend").desc())

print("--- HIGH POTENTIAL CLIENTS ANALYTICS ---")
analytics_df.show()

# 3. Load: Write the clean, optimized data to local storage
# (This creates a 'high_potential_output' folder in your directory)
analytics_df.write.mode("overwrite").parquet("high_potential_output")
print("Data successfully written to local Parquet storage.")

spark.stop()
