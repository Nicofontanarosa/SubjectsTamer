FROM python:3.12.10-slim-bookworm
WORKDIR /app
COPY cert_init/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && mkdir -p /out/ca /out/gateway /out/player-manager /out/collector /out/game-manager /out/encounter \
    && chown -R 10001:10001 /out
COPY cert_init/generate.py .
USER 10001:10001
CMD ["python", "generate.py"]
