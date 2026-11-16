# Immagine base: Python 3.12 su una distribuzione Linux essenziale.
FROM python:3.12.10-slim-bookworm
# Directory di lavoro per i comandi successivi dentro il container.
WORKDIR /app
# Copia le dipendenze prima del codice, per sfruttare la cache della build.
COPY player_manager/requirements.txt .
# Installa le librerie, crea un utente non privilegiato e prepara /data.
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --system --uid 10001 --create-home appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
# Copia i moduli condivisi e i sorgenti del Player Manager.
COPY common /app/common
COPY player_manager/app.py /app/app.py
COPY player_manager/component /app/component
COPY player_manager/database /app/database
# Aggiunge il file JSON utilizzato dall’endpoint /tutorial.
COPY shared/tutorial.json /app/tutorial.json
# Esegue il servizio come utente non root (UID e GID 10001).
USER 10001:10001
# Documenta la porta interna usata dal processo HTTP.
EXPOSE 5005
# Avvia Gunicorn con due processi worker; app:app = file app.py, variabile app.
CMD ["gunicorn", "--bind", "0.0.0.0:5005", "--workers", "2", "app:app"]

# ============================================================
# ESEMPI DI UTILIZZO (dalla cartella del docker-compose.yml)
# ============================================================
# docker compose build player-manager  -> ricostruisce l’immagine del servizio.
# docker compose up -d player-manager  -> avvia il servizio e le sue dipendenze.
# docker compose logs -f player-manager -> visualizza i log.
# ATTENZIONE: questo Dockerfile viene letto durante la build, non a ogni richiesta.