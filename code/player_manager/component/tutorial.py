"""Tutorial content loading."""

# json legge il file del tutorial; Path gestisce il suo percorso.
import json
import os
from pathlib import Path

from flask import current_app, jsonify

from common.game import error_response


# Legge TUTORIAL_PATH dall’ambiente; per default usa /app/tutorial.json.
TUTORIAL_PATH = Path(os.environ.get("TUTORIAL_PATH", "/app/tutorial.json"))


# Carica il tutorial da file e lo restituisce come JSON HTTP.
def tutorial():
    try:
        # Il with chiude il file automaticamente; json.load lo converte in dati Python.
        with TUTORIAL_PATH.open(encoding="utf-8") as tutorial_file:
            return jsonify(json.load(tutorial_file)), 200
    # File assente/non leggibile o JSON non valido: log e risposta 500.
    except (OSError, json.JSONDecodeError):
        current_app.logger.exception("Tutorial file could not be read")
        return error_response("tutorial_unavailable", "The field guide is unavailable", 500)

# ======================================================================
# ESEMPIO DI CHIAMATA HTTP
# ======================================================================
# GET /tutorial
# -> apre /app/tutorial.json e restituisce il JSON contenuto nel file.
# Se il file è mancante o non valido, restituisce errore HTTP 500.
# Il Dockerfile copia shared/tutorial.json proprio in /app/tutorial.json.