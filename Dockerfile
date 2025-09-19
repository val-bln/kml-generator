FROM python:3.11-slim

# Installation des dépendances système pour Tippecanoe
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    libsqlite3-dev \
    zlib1g-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Installation de Tippecanoe avec gestion d'erreurs
RUN git clone https://github.com/felt/tippecanoe.git /tmp/tippecanoe && \
    cd /tmp/tippecanoe && \
    make -j$(nproc) && \
    make install && \
    rm -rf /tmp/tippecanoe && \
    tippecanoe --version

# Configuration Python
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code
COPY . .

# Port d'exposition
EXPOSE 8000

# Commande de démarrage
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]