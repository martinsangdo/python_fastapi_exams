from kafka import KafkaConsumer
from kafka import TopicPartition

topic_name = 'my-topic-1'
bootstrap_servers = ['localhost:9092']

# Initialize consumer (we don't need to subscribe, just connect)
consumer = KafkaConsumer(bootstrap_servers=bootstrap_servers)

# Get all partition IDs for the topic
partitions = consumer.partitions_for_topic(topic_name)

if partitions is None:
    print(f"❌ Topic '{topic_name}' does not exist.")
    exit()

total_messages = 0

# Loop through each partition to find the message count
for p in partitions:
    tp = TopicPartition(topic_name, p)
    
    # Get the earliest available offset (usually 0, unless retention deleted old data)
    beginning_offset = consumer.beginning_offsets([tp])[tp]
    
    # Get the latest offset (the end of the log)
    end_offset = consumer.end_offsets([tp])[tp]
    
    # Messages in this partition = End Offset - Beginning Offset
    partition_count = end_offset - beginning_offset
    total_messages += partition_count
    
    print(f"📦 Partition {p}: {partition_count} messages")

print(f"\n📊 Total active messages in '{topic_name}': {total_messages}")

consumer.close()