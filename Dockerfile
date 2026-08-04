FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SYSTEM_DB=/data/system.sqlite \
    PHOTOS_DIR=/data/photos \
    LOGBOOK_UPLOAD_DIR=/data/logbook_uploads \
    MAX_UPLOAD_MB=256 \
    SECRET_KEY=change-me-in-production \
    INIT_ADMIN_USER=admin \
    INIT_ADMIN_PASSWORD=admin \
    PORT=5000

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY photos_store.py .
COPY logbook_store.py .
COPY users_store.py .
COPY auth_helpers.py .
COPY static ./static

RUN mkdir -p /data/photos /data/logbook_uploads

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "server:app"]
