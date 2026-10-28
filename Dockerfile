# CLSNP MC Marker — single container (static UI + OMR API)
# From repo root:  docker build -t clsnp-mc-marker .
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api/main.py .
COPY api/omr ./omr
# main.py resolves UI as Path(__file__).parent.parent / "web" → /web
COPY web /web

ENV PORT=8080
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
