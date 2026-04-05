FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libasound2 \
    libasound2-plugins \
    libfreetype6 \
    libcurl4 \
    libgcc-s1 \
    libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir -r requirements.txt \
    && mkdir -p /app/audio

# Configure ALSA null device so voicepeak CLI can run without /dev/snd
RUN echo 'pcm.!default { type null }\nctl.!default { type null }' > /etc/asound.conf

COPY src/ .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
