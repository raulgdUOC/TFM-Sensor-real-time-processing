from confluent_kafka import Consumer, KafkaException, KafkaError
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client import InfluxDBClient, Point
import json
import os


# Kafka config
kafka_config = {
    'bootstrap.servers': 'my-cluster-kafka-brokers:9092',  # Kafka server
    'group.id': 'raw-data',                # Consummer group
    'auto.offset.reset': 'earliest',       # From the beggining in case of no offset
}

kafka_topics = ['temperature-topic', 
                'p1-topic', 
                'p2-topic', 
                'humidity-topic', 
                'pressure-topic', 
                'noise-laeq-topic', 
                'noise-lamin-topic', 
                'noise-lamax-topic']

# InfluxDB config
influxdb_url = "http://my-influxdb-influxdb2:80"
influxdb_token = os.getenv("INFLUXDB_TOKEN")
influxdb_org = "influxdata"
influxdb_bucket = "Raw data"

# Start client InfluxDB
influxdb_client = InfluxDBClient(url=influxdb_url, token=influxdb_token, org=influxdb_org)
write_api = influxdb_client.write_api(write_options=SYNCHRONOUS)

# Create kafka consumer
consumer = Consumer(kafka_config)
consumer.subscribe(kafka_topics)

def parse_and_write_to_influxdb(message):
    try:
        # Parse to JSON
        data = json.loads(message)
        
        # Take the relevants fields
        sensor_type = data['sensor']['sensor_name']
        timestamp = data['timestamp']
        location = data['location']
        value = float(data['sensordatavalues']['value'])
        value_type = data['sensordatavalues']['value_type']

        # Create a influxdb point
        point = Point(value_type) \
            .tag("sensor_type", sensor_type) \
            .tag("country", location['country']) \
            .tag("location", location['location']) \
            .field("latitude", float(location['latitude'])) \
            .field("longitude", float(location['longitude'])) \
            .field(value_type, float(value)) \
            .time(timestamp)

        # Write in influxdb
        write_api.write(bucket=influxdb_bucket, org=influxdb_org, record=point)
        print(f"Data written in infludb: {point}")
    except Exception as e:
        print(f"Error processing the message: {e}")

try:
    print("Starting Kafka...")
    while True:
        # Read messages
        msg = consumer.poll(1.0)  # Wait 1 seccond per message

        if msg is None:
            continue

        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                print(f"End of the partition {msg.partition()}")
            elif msg.error():
                raise KafkaException(msg.error())
        else:
            # Process message
            value = msg.value().decode('utf-8')
            print(f"Message received: {value}")
            parse_and_write_to_influxdb(value)

except KeyboardInterrupt:
    print("Consumption interrupted by the user")
finally:
    # Cerrar conexiones
    print("Closing Kafka consumer and InfluxDB client...")
    consumer.close()
    influxdb_client.close()
