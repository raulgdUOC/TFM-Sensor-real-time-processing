FROM python:3.12-slim-bookworm

RUN pip install --upgrade pip
RUN groupadd -r lirantal && useradd -r -s /bin/false -g lirantal lirantal

COPY requirements.txt /app/requirements.txt
RUN chown -R lirantal:lirantal /app
WORKDIR /app
RUN pip install -r requirements.txt

COPY modelo-1.py modelo-1.py
RUN pip install pandas_datareader
USER root

