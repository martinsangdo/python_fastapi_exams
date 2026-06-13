import json
from kafka import KafkaConsumer

# Initialize the Kafka Consumer
consumer = KafkaConsumer(
    'my-topic-1',
    bootstrap_servers=['localhost:9092'],
    # auto_offset_reset='earliest',  # Start reading from the beginning of the topic
    # group_id='test-group-id-1',  #used for multiple consumers to share the load
    value_deserializer=lambda x: json.loads(x.decode('utf-8'))
)

print("🎧 Consumer is listening for messages...")
try:
    for message in consumer:
        print(f"Received: {message.value}")
except KeyboardInterrupt:
    print("\nStopping Consumer.")
finally:
    consumer.close()