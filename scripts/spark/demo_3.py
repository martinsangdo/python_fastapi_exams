import os

# Tell Python which Java and Python versions to use for Spark.
# Spark runs on the JVM internally, so it needs Java to start.
os.environ["JAVA_HOME"] = "/opt/homebrew/opt/openjdk@17"
os.environ["PYSPARK_PYTHON"] = "/opt/homebrew/bin/python3.10"
os.environ["PYSPARK_DRIVER_PYTHON"] = "/opt/homebrew/bin/python3.10"

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, expr

# SparkSession is the entry point to everything in Spark.
# .master("local[*]") means: run on this machine using all available CPU cores.
# In production you would point this to a real cluster URL instead.
spark = SparkSession.builder \
    .appName("SimpleStreamingDemo") \
    .master("local[*]") \
    .getOrCreate()

# "rate" is a built-in Spark source that generates fake data automatically.
# It produces one row every interval: (timestamp, value) where value is 0, 1, 2, 3, ...
# rowsPerSecond=2 means Spark emits 2 new rows every second.
# This is perfect for learning — no real data source or files required.
streaming_df = spark.readStream \
    .format("rate") \
    .option("rowsPerSecond", 2) \
    .load()

# Add a new column "status" based on the auto-generated "value".
# This is a transformation — it defines WHAT to do with each row,
# but Spark does not actually run it yet (lazy evaluation).
processed = streaming_df.withColumn(
    "status",
    expr("CASE WHEN value % 3 = 0 THEN 'HIGH' ELSE 'normal' END")
)

# writeStream tells Spark to start consuming the stream and send results somewhere.
# outputMode("append") = only show newly arrived rows each micro-batch (not all history).
# format("console") = print results to the terminal.
# .start() is what actually kicks off the streaming job.
query = processed.writeStream \
    .outputMode("append") \
    .format("console") \
    .option("truncate", False) \
    .start()

print("--- STREAMING ACTIVE (runs for 10 seconds) ---")

# awaitTermination(10) keeps the script alive for 10 seconds so we can see the output.
# Without this the script would exit immediately and kill the stream.
query.awaitTermination(10)

# Always stop the query and session to free up memory and ports.
query.stop()
spark.stop()
