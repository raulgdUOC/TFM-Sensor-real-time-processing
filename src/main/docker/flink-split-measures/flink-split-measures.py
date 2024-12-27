from pyflink.datastream.connectors.kafka import FlinkKafkaConsumer, KafkaSink, KafkaRecordSerializationSchema, DeliveryGuarantee
from pyflink.datastream.execution_mode import RuntimeExecutionMode
from pyflink.common.restart_strategy import RestartStrategies
from pyflink.common.serialization import SimpleStringSchema
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.common import Types
import json


# Kafka config
KAFKA_BROKER = 'my-cluster-kafka-brokers:9092'
INPUT_TOPIC = 'plain-data-sensor'
OUTPUT_TOPICS = {
    "temperature": "temperature-topic",
    "P1": "p1-topic",
    "P2": "p2-topic",
    "humidity": "humidity-topic",
    "pressure_at_sealevel": "pressure-topic",
    "noise_LAeq": "noise-laeq-topic",
    "noise_LA_min": "noise-lamin-topic",
    "noise_LA_max": "noise-lamax-topic"
}
VALUE_TYPES_ALLOWED = list(OUTPUT_TOPICS.keys())


def edge_case(values):
    value_type = values["value_type"]
    value = values["value"]

    if (type(value) == str):
        try:
            value = float(value)
        except ValueError:

            return False

    EDGE_CASES = {
        "temperature": lambda v: -30 < v < 40,
        "P1": lambda v: 0 < v < 500,
        "P2": lambda v: 0 < v < 500,
        "humidity": lambda v: 0 < v < 100,
        "pressure_at_sealevel": lambda v: 85000 < v < 105000,
        "noise_LAeq": lambda v: 30 < v < 120,
        "noise_LA_min": lambda v: 0 < v < 30,
        "noise_LA_max": lambda v: 50 < v < 140,
    }

    return EDGE_CASES[value_type](value)


def parse_data(data, value):
    if (not (edge_case(value)) or data['location']["indoor"]):
        return None
    output_data_template = {}
    output_data_template['id'] = data['id']
    output_data_template['timestamp'] = data['timestamp']
    output_data_template['location'] = {}
    output_data_template['location']['id'] = data['location']['id']
    output_data_template['location']['latitude'] = data['location']['latitude']
    output_data_template['location']['longitude'] = data['location']['longitude']
    output_data_template['location']['country'] = data['location']['country']
    output_data_template['location']['location'] = data['location']['location']
    output_data_template['sensor'] = {}
    output_data_template['sensor']['id'] = data['sensor']['id']
    output_data_template['sensor']['sensor_name'] = data['sensor']['sensor_type']['name']
    output_data_template["sensordatavalues"] = value
    return output_data_template

def split_measures(data):
    try:
        if not isinstance(data, str):
            raise ValueError("Data is not a valid string")
        parsed_data = json.loads(data)
        common_data = {k: v for k, v in parsed_data.items() if k != "sensordatavalues"}
        results = {}
        for value in parsed_data.get("sensordatavalues", []):
            value_type = value.get("value_type")
            if value_type in VALUE_TYPES_ALLOWED:
                output_data = parse_data(common_data, value)
                if output_data == None:
                    results["None"] = json.dumps(output_data)
                else:
                    results[value_type] = json.dumps(output_data)
        return results
    except Exception as e:
        raise ValueError(f"Error parsing data: {e}")



def main():
    kafka_jar = "file:///opt/flink/usrlib/flink-sql-connector-kafka-3.0.2-1.18.jar"
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(1)
    env.add_jars(kafka_jar)
    env.set_runtime_mode(RuntimeExecutionMode.STREAMING)
    env.set_restart_strategy(RestartStrategies.fixed_delay_restart(
    3,  # number of restart attempts
    10000  # delay(millisecond)
    ))

    # Configure kafka consumer
    kafka_consumer = FlinkKafkaConsumer(
        topics=INPUT_TOPIC,
        deserialization_schema=SimpleStringSchema(),
        properties={
            'bootstrap.servers': KAFKA_BROKER,
            'group.id': 'flink-append-by-country',
            'auto.offset.reset': 'earliest',
        }
    )
    kafka_consumer.set_start_from_earliest()

    # Configure kafka producers
    kafka_producers = {
        value_type: KafkaSink.builder() \
        .set_bootstrap_servers(KAFKA_BROKER) \
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
                .set_topic(topic)
                .set_value_serialization_schema(SimpleStringSchema())
                .build()
        ) \
        .set_delivery_guarantee(DeliveryGuarantee.AT_LEAST_ONCE) \
        .build()
        for value_type, topic in OUTPUT_TOPICS.items()
    }

    # Read data from the topics
    input_stream = env.add_source(kafka_consumer)

    # Process the data
    processed_stream = input_stream.map(split_measures)

    # Get the correct data_stream from the dictionary
    def return_dict(data_stream):
        return data_stream[value_type]
    for value_type, producer in kafka_producers.items():
        processed_stream.filter(lambda x: value_type in x.keys()) \
        .map(lambda x: str(return_dict(x)), output_type=Types.STRING()) \
        .sink_to(producer).name(f"Kafka producer: {value_type}")

    # Execute the job
    env.execute(f"Split measures")

if __name__ == "__main__":
    main()
