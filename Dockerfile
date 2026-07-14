FROM python:3.12-slim

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

# Nicht als root laufen; /data ist das Volume fuer settings/users/cache
RUN useradd -r -u 10001 appuser && mkdir -p /data && chown appuser:appuser /data
USER appuser
ENV DATA_DIR=/data
EXPOSE 8090

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
