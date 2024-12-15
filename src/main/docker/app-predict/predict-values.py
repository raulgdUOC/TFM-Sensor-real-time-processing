import numpy as np
import pandas as pd
import tensorflow as tf
import redis
from influxdb_client import InfluxDBClient
import os
from datetime import datetime, timedelta
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client import InfluxDBClient, Point

# Influxdb config
influxdb_url = "http://my-influxdb-influxdb2:80"
influxdb_token = os.getenv("INFLUXDB_TOKEN")
influxdb_org = os.getenv("INFLUXDB_ORG")
influxdb_bucket = os.getenv("INFLUXDB_BUCKET")

influxdb_client = InfluxDBClient(url=influxdb_url, token=influxdb_token, org=influxdb_org)
query_api = influxdb_client.query_api()
write_api = influxdb_client.write_api(write_options=SYNCHRONOUS)

# Redis config
redis_password = os.getenv("REDIS_SECRET")
redis_replicas_host = "my-redis-replicas"
r = redis.Redis(host=redis_replicas_host, port=6379, decode_responses=True, password=redis_password)

# Sensor type value
measurement = os.getenv("MEASUREMENT")

query = f'''
        from(bucket: "{influxdb_bucket}")
        |> range(start: -1h) 
        |> filter(fn: (r) => r._measurement == "{measurement}") 
        |> filter(fn: (r) => r["_field"] == "{measurement}")
        |> group(columns: ["_measurement", "_field", "country", "location"])
        |> aggregateWindow(every: 10m, fn: mean, createEmpty: false) 
        |> yield(name: "agrupados")
        '''
records = []

tables = query_api.query(query)

for table in tables:
    for record in table.records:
        records.append({
            "time": record["_time"],
            "value": record["_value"],
            "measurement": record["_measurement"],
            "country": record["country"],
            "location": record["location"],
        })

df = pd.DataFrame(records)
df['time'] = pd.to_datetime(df['time'])
df.set_index('time', inplace=True)

dict_countries_encoded = r.hgetall(f'countries_encoder_{measurement}')
dict_location_encoded = r.hgetall(f'locations_encoded_{measurement}')

df["country_encoded"] = df["country"].map(dict_countries_encoded).astype('float')
df["location_encoded"] = df["location"].map(dict_location_encoded).astype('float')


df = df.dropna(subset=["country_encoded", "location_encoded"])
df = df.sort_values(['location_encoded', 'time'])

df_transformed = df[["country_encoded", "location_encoded", "value"]]

df_transformed = df

def create_multivariate_rnn_data(data, window_size):
    n = data.shape[0]
    X = []
    for i, j in enumerate(range(window_size, n)):
        window = data[i: j]
        numb_loc = len(set(window["location_encoded"].to_list()))
        if (numb_loc == 1):
            X.append(data[i: j])
    X = np.stack(X, axis=0)
    return X

window_size = 6

X = create_multivariate_rnn_data(df_transformed, window_size=window_size)

model = tf.keras.models.load_model(f"/app-predict/models/{measurement}_lstm.keras")

X_test_sensors = X[:, :, 0].reshape(-1, window_size, 1).astype(float)  # Valores del sensor
X_test_countries = X[:, 0, 4].astype(int)  # Países codificados
X_test_locations = X[:, 0, 5].astype(int)  # Localizaciones codificadas

predicciones = model.predict([X_test_sensors, X_test_countries, X_test_locations])

#predicciones = model.predict(X[:,:,[0,4,5]].astype(float))


timestamp = datetime.now() + timedelta(hours=1)

df_predicciones = pd.DataFrame({"country": X[:,0,2],
                             "location": X[:,0,3],
                             f"{measurement}": predicciones[:,0],
                             "timestamp": timestamp})

points = [
    Point(measurement)
    .tag("country", row['country'])
    .tag("location", row['location'])
    .field(measurement, row[f"{measurement}"])
    .time(row['timestamp'])
    for _, row in df_predicciones.iterrows()
]

# Escritura batch
write_api.write(bucket="predictions", org=influxdb_org, record=points)
