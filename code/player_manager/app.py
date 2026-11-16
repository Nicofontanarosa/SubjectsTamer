"""Endpoint HTTP del Player Manager: ricezione richieste e preparazione risposte."""

import logging

from flask import Flask, jsonify, request

# gunicorn carica app.py come modulo singolo; negli import da package usiamo i percorsi relativi.
if __package__:
    from .component import authentication, player_profile, tutorial as tutorial_component
    from .component.exceptions import (
        ApplicationError, AuthenticationError, ConflictError, DependencyError,
        NotFoundError, StorageError, ValidationError,
    )
    from .database import Database
else:
    from component import authentication, player_profile, tutorial as tutorial_component
    from component.exceptions import (
        ApplicationError, AuthenticationError, ConflictError, DependencyError,
        NotFoundError, StorageError, ValidationError,
    )
    from database import Database


app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# le componenti sollevano eccezioni applicative, app.py decide lo status HTTP.
# in questo modo authentication e player_profile non devono importare Flask.
ERROR_STATUS = {
    ValidationError: 400,
    AuthenticationError: 401,
    NotFoundError: 404,
    ConflictError: 409,
    StorageError: 500,
    DependencyError: 502,
}


@app.errorhandler(ApplicationError)
def handle_application_error(error):
    # manteniamo lo stesso formato degli errori che avevamo prima del refactoring.
    return jsonify({"error": error.code, "message": error.message}), ERROR_STATUS.get(type(error), 500)


def get_json_body():
    # il body di POST/PUT deve essere un oggetto json, non una lista o testo.
    # silent=True evita che Flask restituisca da solo un errore con un formato diverso.
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ValidationError("invalid_request", "A JSON object is required")
    return body


def player_response_data(player):
    # qui trasformiamo i nomi delle colonne del db nel formato JSON pubblico.
    # password_hash rimane nel database e non viene mai incluso nella risposta.
    return {
        "playerId": player["player_id"],
        "email": player["email"],
        "nickname": player["nickname"],
        "avatar": player["avatar"],
        "bio": player["bio"],
        "createdAt": player["created_at"],
    }


# POST /players: leggiamo il body e deleghiamo la registrazione alla componente.
@app.post("/players")
def register_player():
    player = authentication.register_player(get_json_body())
    return jsonify({"player": player_response_data(player)}), 201


# POST /auth/login: la componente verifica le credenziali, qui prepariamo la risposta.
@app.post("/auth/login")
def login():
    player = authentication.login(get_json_body())
    return jsonify({"player": player_response_data(player)}), 200


# per ora non abbiamo sessioni o token da invalidare: logout restituisce solo 204.
@app.post("/auth/logout")
def logout():
    return "", 204


# <player_id> arriva dall'URL; la componente recupera il player dal database.
@app.get("/players/<player_id>")
def get_player(player_id):
    player = player_profile.get_player(player_id)
    return jsonify({"player": player_response_data(player)}), 200


# PUT /players/<player_id>: i dati nuovi arrivano dal JSON della richiesta.
@app.put("/players/<player_id>")
def update_player(player_id):
    player = player_profile.update_player(player_id, get_json_body())
    return jsonify({"player": player_response_data(player)}), 200


# DELETE /players/<player_id>: la componente elimina i dati, app.py risponde senza body.
@app.delete("/players/<player_id>")
def delete_player(player_id):
    player_profile.delete_player(player_id)
    return "", 204


# GET /tutorial: la componente legge il file, app.py lo restituisce come JSON.
@app.get("/tutorial")
def tutorial():
    data = tutorial_component.tutorial()
    return jsonify(data), 200


# endpoint usato dagli healthcheck docker, non serve una componente dedicata.
@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "player-manager"}), 200


# prepara il database prima che il worker inizi a gestire richieste http.
with app.app_context():
    Database.initialize_database()