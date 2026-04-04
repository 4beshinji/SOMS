FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ .
COPY config/ /app/config/

RUN groupadd -g 1000 appuser && useradd -u 1000 -g appuser -d /app appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["python", "main.py"]
