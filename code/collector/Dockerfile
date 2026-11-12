FROM python:3.12.10-slim-bookworm
WORKDIR /app
COPY collector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --system --uid 10001 --create-home appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
COPY common /app/common
COPY shared /app/shared
COPY collector/app.py /app/app.py
COPY frontend/assets /app/assets
USER 10001:10001
EXPOSE 5005
CMD ["gunicorn", "--bind", "0.0.0.0:5005", "--workers", "2", "app:app"]
