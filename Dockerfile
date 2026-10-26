FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Instala ffmpeg e dependencias de sistema para audio/video (OpenCV / PyAV)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instala pacotes Python utilizados pelo RVM
RUN pip install --no-cache-dir \
    flask>=3.1.0 \
    pyyaml \
    faster-whisper>=1.2.0 \
    ctranslate2>=4.8.0 \
    onnxruntime \
    opencv-python-headless \
    av \
    pillow \
    numpy \
    httpx \
    websockets \
    yt-dlp \
    pycryptodomex \
    tqdm

# Copia os arquivos do projeto
COPY . /app

# Cria diretorios de persistencia
RUN mkdir -p /app/saida /app/trabalho

EXPOSE 5050

# Inicia o servidor web na porta 5050
CMD ["python", "-m", "http.server", "5050", "--directory", "_internal/agente/static"]
