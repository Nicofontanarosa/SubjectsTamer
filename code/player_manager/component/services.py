"""Indirizzi dei servizi interni e funzione comune per le richieste HTTP."""

import os

import requests

# in docker i nomi dei servizi si risolvono sulla rete interna del compose.
# rstrip elimina l'eventuale slash finale prima di aggiungere il percorso dell'endpoint.
COLLECTOR_URL = os.environ.get("COLLECTOR_URL", "http://collector:5005").rstrip("/")
ENCOUNTER_URL = os.environ.get("ENCOUNTER_URL", "http://encounter:5005").rstrip("/")
GAME_MANAGER_URL = os.environ.get("GAME_MANAGER_URL", "http://game-manager:5005").rstrip("/")


# invia la richiesta al microservizio e restituisce l'oggetto requests.Response.
# gli errori di rete vengono gestiti dalle componenti che chiamano questa funzione.
def internal_request(method, url, *, json_body=None):
    return requests.request(method, url, json=json_body, timeout=5)