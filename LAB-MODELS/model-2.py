import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import mean_absolute_error
import tensorflow as tf
from tensorflow.keras.callbacks import ModelCheckpoint, EarlyStopping
from tensorflow.keras.models import Model
from tensorflow.keras.layers import Dense, LSTM, Input, Embedding, Flatten, Concatenate
from sklearn.preprocessing import LabelEncoder
import redis
from influxdb_client import InfluxDBClient



# Path to save the models
results_path = Path('results', 'time_series')
if not results_path.exists():
    results_path.mkdir(parents=True)

# Redis config
redis_master = "localhost"
redis_replicas = "localhost"
redis_secret = "Sjr6U9ggmz"
w = redis.Redis(host=redis_master, port=6379, decode_responses=True, password=redis_secret)
r = redis.Redis(host=redis_replicas, port=6379, decode_responses=True, password=redis_secret)



# InfluxDB config
influxdb_url = "http://localhost:8086"
influxdb_token = "1GKO2niitYYDPocWI9PH1WxfB5b28FUE"
influxdb_org = "influxdata"
influxdb_bucket = "Raw data"
measurement = "noise_LA_max"

influxdb_client = InfluxDBClient(url=influxdb_url, token=influxdb_token, org=influxdb_org)
query_api = influxdb_client.query_api()

query = f'''
        from(bucket: "{influxdb_bucket}")
        |> range(start: -4d) 
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

# Processing
countries = list(set(df["country"].to_list()))
locations = list(set(df["location"].to_list()))

n_countries = len(countries)
n_locations = len(locations)

encoder_country = LabelEncoder()
encoder_location = LabelEncoder()

encoder_country.fit(countries)
encoder_location.fit(locations)

dict_countries_encoded = {country: idx for idx, country in enumerate(encoder_country.classes_)}
dict_locations_encoded = {location: idx for idx, location in enumerate(encoder_location.classes_)}

w.hmset(f'countries_encoder_{measurement}', dict_countries_encoded)
w.hmset(f'locations_encoded_{measurement}', dict_locations_encoded)

df["country_encoded"] = encoder_country.transform(df["country"])
df["location_encoded"] = encoder_location.transform(df["location"])
df = df.sort_values(['location_encoded', 'time'])

df_transformed = df[["country_encoded", "location_encoded", "value"]]

# Función para generar datos para la RNN
def create_multivariate_rnn_data(data, window_size):
    y = data['value'][window_size:]
    y_reset_index = y.reset_index()
    n = data.shape[0]
    X = []
    for i, j in enumerate(range(window_size, n)):
        window = data[i: j]
        numb_loc = len(set(window["location_encoded"].to_list()))
        if (numb_loc == 1) & (data["location_encoded"].iloc[j] in window["location_encoded"].to_list()):
            X.append(data[i: j])
        else:
            y_reset_index = y_reset_index.drop(i)
    y = y_reset_index.set_index('time')
    X = np.stack(X, axis=0)
    return X, y

window_size = 6

X, y = create_multivariate_rnn_data(df_transformed, window_size=window_size)

test_size = int(y.shape[0] * 0.1)
train_size = X.shape[0] - test_size

X_train, y_train = X[:train_size], y[:train_size]
X_test, y_test = X[train_size:], y[train_size:]

# Prepare data for the training
X_train_sensors = X_train[:, :, 2].reshape(-1, window_size, 1)
X_train_countries = X_train[:, 0, 0]
X_train_locations = X_train[:, 0, 1]

X_test_sensors = X_test[:, :, 2].reshape(-1, window_size, 1)
X_test_countries = X_test[:, 0, 0]
X_test_locations = X_test[:, 0, 1]

# Model parameters
embedding_dim_country = 4
embedding_dim_location = 4
lstm_units = 12
dense_units = 6
output_size = 1

sensor_input = Input(shape=(window_size, 1), name='Sensor_Input')
country_input = Input(shape=(1,), name='Country_Input')
location_input = Input(shape=(1,), name='Location_Input')

country_embedding = Embedding(input_dim=n_countries, output_dim=embedding_dim_country, name='Country_Embedding')(country_input)
country_embedding = Flatten()(country_embedding)

location_embedding = Embedding(input_dim=n_locations, output_dim=embedding_dim_location, name='Location_Embedding')(location_input)
location_embedding = Flatten()(location_embedding)

categorical_features = Concatenate()([country_embedding, location_embedding])
sensor_reshaped = Dense(embedding_dim_country + embedding_dim_location, activation='relu')(sensor_input)
from tensorflow.keras.layers import RepeatVector

# Expandir categorical_features para que coincida con la dimensión temporal de sensor_reshaped
categorical_features_expanded = RepeatVector(window_size)(categorical_features)

# Concatenar las características temporales y las categóricas
merged_features = Concatenate(axis=-1)([sensor_reshaped, categorical_features_expanded])

lstm_output = LSTM(units=lstm_units, dropout=0.1, recurrent_dropout=0.1)(merged_features)
dense_output = Dense(dense_units, activation='relu')(lstm_output)
output = Dense(output_size, activation='linear')(dense_output)

lstm_model = Model(inputs=[sensor_input, country_input, location_input], outputs=output)
lstm_model.compile(loss='mae', optimizer='RMSProp')

# Entrenamiento
lstm_path = (results_path / f'{measurement}_lstm.keras').as_posix()

checkpointer = ModelCheckpoint(filepath=lstm_path, verbose=1, monitor='val_loss', mode='min', save_best_only=True)
early_stopping = EarlyStopping(monitor='val_loss', patience=10, restore_best_weights=True)

result_lstm = lstm_model.fit(
    [X_train_sensors, X_train_countries, X_train_locations],
    y_train,
    epochs=50,
    batch_size=20,
    shuffle=False,
    validation_data=([X_test_sensors, X_test_countries, X_test_locations], y_test),
    callbacks=[early_stopping, checkpointer],
    verbose=1
)

# Evaluación
y_pred = lstm_model.predict([X_test_sensors, X_test_countries, X_test_locations])
mae = mean_absolute_error(y_test, y_pred)
print(f'Mean Absolute Error: {mae}')
