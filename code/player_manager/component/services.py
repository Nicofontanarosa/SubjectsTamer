"""Internal HTTP calls and service addresses."""

import os

import requests


# URL interne dei servizi Docker; rstrip("/") evita una / finale doppia.
COLLECTOR_URL = os.environ.get("COLLECTOR_URL", "http://collector:5005").rstrip("/")
ENCOUNTER_URL = os.environ.get("ENCOUNTER_URL", "http://encounter:5005").rstrip("/")
GAME_MANAGER_URL = os.environ.get("GAME_MANAGER_URL", "http://game-manager:5005").rstrip("/")


# Esegue la richiesta HTTP; timeout=5 limita l’attesa a 5 secondi per fase.
def internal_request(method, url, *, json_body=None):
    return requests.request(method, url, json=json_body, timeout=5)

# ======================================================================
# ESEMPI DI UTILIZZO
# ======================================================================
# response = internal_request("POST", f"{COLLECTOR_URL}/internal/players/123/collection/initialize")
# -> contatta Collector e restituisce un oggetto requests.Response.
#
# response = internal_request("DELETE", f"{ENCOUNTER_URL}/internal/players/123/encounters")
# -> richiede a Encounter di eliminare gli incontri del player.
#
# response = internal_request("POST", "http://servizio:5005/endpoint", json_body={"id": "123"})
# -> invia un corpo JSON. Il parametro json_body è solo nominato (*).