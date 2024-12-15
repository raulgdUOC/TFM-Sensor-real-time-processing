FROM python:3.12-slim-bookworm

RUN pip install --upgrade pip
RUN groupadd -r lirantal && useradd -r -s /bin/false -g lirantal lirantal

COPY . /app/
RUN chown -R lirantal:lirantal /app
WORKDIR /app
RUN pip install -r /app/requirements.txt
USER lirantal
CMD python3 from-kafka-to-influxdb-raw.py
