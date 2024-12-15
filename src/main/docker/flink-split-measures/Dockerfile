FROM pyflink-base:latest

# Download the connector dependency for kafka
RUN wget -P /opt/flink/usrlib https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-kafka/3.0.2-1.18/flink-sql-connector-kafka-3.0.2-1.18.jar
RUN ln -sf $(which python3) /usr/bin/python
RUN pip3 install google-cloud-bigquery-storage

ADD --chown=flink:flink flink-split-measures.py /opt/flink/usrlib/flink-split-measures.py
