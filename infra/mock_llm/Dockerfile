FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi==0.109.0 uvicorn==0.27.0 python-multipart==0.0.6

COPY main.py .

RUN groupadd -g 1000 appuser && useradd -u 1000 -g appuser -d /app appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
