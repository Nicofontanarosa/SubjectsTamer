"""HTTP entry point for the Player Manager microservice."""

import logging

from flask import Flask, request, jsonify

# Se app.py viene importato come package, usa import relativi.
if __package__:
    from .component import (
        authentication,
        player_profile,
        tutorial as tutorial_component,
    )
    from .database import Database

# Se Gunicorn importa app.py direttamente, usa import assoluti.
else:
    from component import (
        authentication,
        player_profile,
        tutorial as tutorial_component,
    )
    from database import Database

# Crea l’app Flask e configura i messaggi di log.
app = Flask(__name__)
app.logger.setLevel(logging.INFO)


# POST /players: passa il JSON alla componente authentication per registrare il giocatore.
@app.post("/players")
def register_player():
    return authentication.register_player(request.get_json(silent=True))


# POST /auth/login: controlla le credenziali.
@app.post("/auth/login")
def login():
    return authentication.login(request.get_json(silent=True))


# POST /auth/logout: termina la richiesta con risposta 204.
@app.post("/auth/logout")
def logout():
    return authentication.logout()


# <player_id> è un parametro nell’URL, passato alla funzione.
@app.get("/players/<player_id>")
def get_player(player_id):
    return player_profile.get_player(player_id)


# PUT /players/<player_id>: aggiorna il profilo.
@app.put("/players/<player_id>")
def update_player(player_id):
    return player_profile.update_player(player_id, request.get_json(silent=True))


# DELETE /players/<player_id>: richiede la rimozione del giocatore.
@app.delete("/players/<player_id>")
def delete_player(player_id):
    return player_profile.delete_player(player_id)


# GET /tutorial: restituisce il contenuto del tutorial JSON.
@app.get("/tutorial")
def tutorial():
    return tutorial_component.tutorial()


# GET /health: endpoint usato dagli healthcheck Docker.
@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "player-manager"}), 200


# All’avvio inizializza la tabella players con il contesto Flask attivo.
with app.app_context():
    Database.initialize_database()

# ======================================================================
# ESEMPI DI CHIAMATE HTTP (dal terminale del computer)
# ======================================================================
# curl http://127.0.0.1:5000/health  # controlla lo stato del gateway
# curl http://127.0.0.1:5000/tutorial
# curl http://127.0.0.1:5000/players/123
# curl -X POST http://127.0.0.1:5000/auth/login \
#      -H 'Content-Type: application/json' \
#      -d '{"email":"mario@example.com","password":"password-di-esempio"}'
# Nota: la porta 5000 è quella del Gateway nel Docker Compose.
# Il Gateway deve inoltrare l’endpoint al Player Manager.
