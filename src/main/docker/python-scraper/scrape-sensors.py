
from concurrent.futures import ThreadPoolExecutor
from geopy.geocoders import Nominatim
from confluent_kafka import Producer
import threading
import requests
import redis
import json
import time
import os

lock = threading.Lock()

def get_place(id_location, lat_log):
    key = f"{id_location}"

    if r.exists(key):
        return r.hgetall(key)
    else:
        with lock:  
            time.sleep(1) 
            try:
                location = geolocator.reverse((lat_log[0], lat_log[1]), language='en')
                if location and "city" in location.raw['address']:
                    city = location.raw['address']['city']
                elif location and "town" in location.raw['address']:
                    city = location.raw['address']['town']
                elif location and "village" in location.raw['address']:
                    city = location.raw['address']['village']
                elif location and "city_district" in location.raw['address']:
                    city = location.raw['address']['city_district']
                elif location and "county" in location.raw['address']:
                    city = location.raw['address']['county']
                elif location and "quarter" in location.raw['address']:
                    city = location.raw['address']['quarter']
        
                else:
                    city = "Unknown"

                country = location.raw['address']['country']
                post_location(key, city, country)
                
                return {"location": city, "country": country}
            except Exception as e:
                print(f"Geocoding error for {lat_log}: {e}")
                post_location(key, "Unknown", "Unknown")
                return {"location": "Unknown", "country": "Unknown"}


def post_location(key, location, country):
    w.hset(key, mapping={"location": location, "country": country})

def process_sensor_data(sensor):
    id_location = sensor["location"]["id"]
    lat_log = (sensor["location"]["latitude"], sensor["location"]["longitude"])
    if lat_log == ("0", "0"):
        return None
    place = get_place(id_location, lat_log)
    sensor["location"]["location"] = place["location"]
    sensor["location"]["country_abb"] = sensor["location"]["country"] 
    sensor["location"]["country"] = place["country"]

    producer.produce("plain-data-sensor", json.dumps(sensor).encode('utf-8'))
    

if __name__ == "__main__":

    # Kafka config
    producer_config = {
        'bootstrap.servers': 'my-cluster-kafka-plain-bootstrap:9092'
    }

    # Url of the data
    url = "https://data.sensor.community/static/v1/data.json"
    
    # Redis config
    redis_secret = os.getenv("REDIS_SECRET")
    redis_master = "my-redis-master"
    redis_replicas = 'my-redis-replicas'

    # Geopy api client
    geolocator = Nominatim(user_agent="other-agent")

    # Start redis clients 
    w = redis.Redis(host=redis_master, port=6379, decode_responses=True, password=redis_secret)
    r = redis.Redis(host=redis_replicas, port=6379, decode_responses=True, password=redis_secret)
    producer = Producer(producer_config)

    response = requests.get(url)

    if response.status_code == 200:
        print("response exitosa:")
        datos = response.json()

        # Limit number of threads
        max_threads = 100  
        with ThreadPoolExecutor(max_threads) as executor:
            futures = [executor.submit(process_sensor_data, sensor) for sensor in datos]
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    print(f"Error processing the message: {e}")

    else:
        print(f"Error requesting the data: {response.status_code}")
    producer.flush()
