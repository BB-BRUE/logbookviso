FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOGBOOK_DB=/data/logbook.sqlite \
    PHOTOS_DB=/data/photos.sqlite \
    PHOTOS_DIR=/data/photos \
    MAX_UPLOAD_MB=256 \
    PORT=5000

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY photos_store.py .
COPY static ./static

RUN mkdir -p /data/photos

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "server:app"]
