"""Microservice health response."""

# jsonify converte il dizionario Python in una risposta JSON.
from flask import jsonify


# Endpoint usato dagli healthcheck di Docker per verificare la risposta HTTP.
def health():
    return jsonify({"status": "ok", "service": "player-manager"}), 200

# ======================================================================
# ESEMPIO DI CHIAMATA HTTP
# ======================================================================
# GET /health
# -> HTTP 200, JSON: {"status": "ok", "service": "player-manager"}
# Esempio dal container: curl http://localhost:5005/health
# Un 200 indica che l’endpoint risponde, non che tutti gli altri servizi funzionino.