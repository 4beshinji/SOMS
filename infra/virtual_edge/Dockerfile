FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir paho-mqtt==2.0.0 python-dotenv==1.0.0

COPY src/ .

RUN groupadd -g 1000 appuser && useradd -u 1000 -g appuser -d /app appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["python", "main.py"]
