from pyspark.sql import SparkSession
from pyspark.sql.functions import explode, split, col, lower

# 1. Initialize a local Spark Session using all available CPU cores (*)
spark = SparkSession.builder \
    .appName("BeginnerBatchDemo") \
    .master("local[*]") \
    .getOrCreate()

# 2. Create a mock dataset (Simulating reading a text file)
data = [("Apache Spark is a fast and general-purpose cluster-computing system"),
        ("Spark provides high-level APIs in Java Scala Python and R"),
        ("PySpark allows data engineers to run Spark workloads using Python")]

df = spark.createDataFrame([(line,) for line in data], ["text_line"])

# 3. Transformation: Split lines into words, lowercase them, and count occurrences
word_counts = df.select(explode(split(lower(col("text_line")), " ")).alias("word")) \
    .groupBy("word") \
    .count() \
    .orderBy(col("count").desc())

# 4. Action: Show the results in the terminal
print("--- BATCH PROCESSING RESULT ---")
word_counts.show(10)

# Stop the session to free local memory
spark.stop()
