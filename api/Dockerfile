FROM python:3.11-slim

# Installation des dépendances système minimales
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    libsqlite3-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Installation de Tippecanoe
RUN git clone https://github.com/felt/tippecanoe.git /tmp/tippecanoe && \
    cd /tmp/tippecanoe && \
    make -j2 && \
    make install && \
    rm -rf /tmp/tippecanoe

# Configuration Python
WORKDIR /app
COPY requirements.txt .
RUN pip3 install -r requirements.txt

# Copie du code
COPY . .

# Port d'exposition
EXPOSE 8000

# Commande de démarrage
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]