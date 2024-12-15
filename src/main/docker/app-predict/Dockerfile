
FROM python:3.12-slim-bookworm

# Copy and install the dependencies
COPY requirements.txt /app-predict/requirements.txt  
WORKDIR /app-predict
RUN pip install -r requirements.txt

# Copy the models and the application to predict the values
COPY models /app-predict/models
COPY predict-values.py /app-predict/predict-values.py

CMD ["python3", "predict-values.py"]

