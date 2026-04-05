FROM rocm/pytorch:rocm7.2.1_ubuntu24.04_py3.12_pytorch_release_2.9.1

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg libsndfile1 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/stt/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY services/stt/src/ .

ENV HSA_OVERRIDE_GFX_VERSION=12.0.1
ENV UVICORN_HOST=0.0.0.0
ENV UVICORN_PORT=8000

EXPOSE 8000
CMD ["python", "main.py"]
