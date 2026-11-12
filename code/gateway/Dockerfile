FROM python:3.12.10-slim-bookworm
WORKDIR /app
COPY gateway/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --system --uid 10001 --create-home appuser \
    && chown -R appuser:appuser /app
COPY common /app/common
COPY gateway/app.py /app/app.py
USER 10001:10001
EXPOSE 5005
CMD ["gunicorn", "--bind", "0.0.0.0:5005", "--workers", "2", "--certfile", "/certs/server.pem", "--keyfile", "/certs/server-key.pem", "app:app"]
