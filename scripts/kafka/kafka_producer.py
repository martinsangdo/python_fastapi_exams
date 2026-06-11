import json
import time
from kafka import KafkaProducer

# Initialize the Kafka Producer
producer = KafkaProducer(
    bootstrap_servers=['localhost:9092'],
    value_serializer=lambda v: json.dumps(v).encode('utf-8')    # Serialize data to JSON and encode to bytes
)

print("🚀 Starting Producer... Sending messages every 2 seconds.")
# Send 5 messages to the topic 'my-topic-1' every 2 seconds
for i in range(1, 6):
    data = {'id': i, 'message': f'Hello Kafka message number {i}!'}
    producer.send('my-topic-1', value=data)
    print(f"Sent: {data}")
    time.sleep(2)

# Ensure all messages are sent before closing
producer.flush()
producer.close()
print("✅ Done sending messages.")