"""Registration, login, and logout operations."""

# re valida il formato dell’email; uuid genera ID univoci; datetime registra l’orario.
import re
import uuid
from datetime import datetime, timezone

# requests serve a riconoscere gli errori delle chiamate HTTP verso Collector.
import requests
from flask import current_app, jsonify
# Le password vengono salvate come hash e confrontate senza decifrarle.
from werkzeug.security import check_password_hash, generate_password_hash

from common.game import error_response

# Supporta sia l’avvio diretto di app.py sia l’import come package.
if __package__ == "component":
    from database import Database
else:
    from ..database import Database

from .player_profile import player_profile
from .services import COLLECTOR_URL, internal_request


# Riceve il JSON della registrazione come dizionario Python.
def register_player(body):
    if not isinstance(body, dict):
        return error_response("invalid_request", "A JSON object is required", 400)
    # Estrae i campi; avatar e bio hanno un valore predefinito.
    email = body.get("email")
    password = body.get("password")
    nickname = body.get("nickname")
    avatar = body.get("avatar", "ranger")
    bio = body.get("bio", "")
    # Controlla i dati prima di scriverli nel database.
    if not isinstance(email, str) or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()):
        return error_response("invalid_email", "Enter a valid email address", 400)
    if not isinstance(password, str) or len(password) < 10:
        return error_response("weak_password", "Password must contain at least 10 characters", 400)
    if not isinstance(nickname, str) or not nickname.strip() or len(nickname.strip()) > 32:
        return error_response("invalid_nickname", "Nickname must contain 1 to 32 characters", 400)
    if not isinstance(avatar, str) or len(avatar) > 40 or not isinstance(bio, str) or len(bio) > 500:
        return error_response("invalid_profile", "Avatar or biography is too long", 400)

    # Crea un nuovo ID e la data di registrazione in UTC.
    player_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    # Salva il player: il with esegue commit oppure rollback e chiude la connessione.
    try:
        with Database() as db:
            db.execute(
                """INSERT INTO players
                   (player_id, email, password_hash, nickname, avatar, bio, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    player_id,
                    email.strip().lower(),
                    generate_password_hash(password),
                    nickname.strip(),
                    avatar,
                    bio.strip(),
                    created_at,
                ),
            )
    # Gestisce i duplicati di email/nickname imposti dai vincoli UNIQUE.
    except Database.IntegrityError as exc:
        if "UNIQUE constraint failed" in str(exc):
            return error_response("account_exists", "Email or nickname is already in use", 409)
        current_app.logger.exception("Could not create player account")
        return error_response("storage_error", "The account could not be created", 500)
    except Database.Error: #qui cattiura altri errori generici di database, come problemi di connessione o di scrittura, non relativi ai vincoli di integrità. Questi errori possono essere causati da problemi temporanei o da configurazioni errate del database.
        current_app.logger.exception("Could not create player account")
        return error_response("storage_error", "The account could not be created", 500)

    try:
        # Chiede a Collector di preparare la collezione iniziale del player.
        response = internal_request(
            "POST",
            f"{COLLECTOR_URL}/internal/players/{player_id}/collection/initialize",
        )
        if response.status_code not in (200, 201):
            current_app.logger.error("Collector initialization failed: %s", response.status_code)
            with Database() as db:
                # Se Collector fallisce, elimina il player appena creato.
                db.execute("DELETE FROM players WHERE player_id = ?", (player_id,))
            return error_response("initialization_failed", "The starting collection could not be created", 502)
    # Gestisce gli errori di rete o timeout verso Collector.
    except requests.RequestException:
        current_app.logger.exception("Collector could not be reached during registration")
        # Se Collector non risponde, elimina il player appena creato.
        with Database() as db:
            db.execute("DELETE FROM players WHERE player_id = ?", (player_id,))
        return error_response("service_unavailable", "The collection service is unavailable", 502)

    # Rilegge il player e restituisce il profilo nella risposta HTTP 201.
    with Database() as db:
        row = db.fetch_one("SELECT * FROM players WHERE player_id = ?", (player_id,))
        # in row dovrebbe esserci il nuovo player appena creato; se non c’è, è un errore interno.
    return jsonify({"player": player_profile(row)}), 201


# Login: cerca il player per email e verifica la password salvata come hash.
def login(body):
    if not isinstance(body, dict):
        return error_response("invalid_request", "A JSON object is required", 400)
    #estraggo email e password dal body della richiesta.
    email, password = body.get("email"), body.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        return error_response("invalid_credentials", "Email or password is incorrect", 401)
    #controllo che siano stringhe, altrimenti restituisco errore 401.
    with Database() as db:
        row = db.fetch_one(
            "SELECT * FROM players WHERE email = ?",
            (email.strip().lower(),),
        )
    # Stessa risposta 401 se l’email manca o la password è sbagliata.
    if row is None or not check_password_hash(row["password_hash"], password):
        return error_response("invalid_credentials", "Email or password is incorrect", 401)
    return jsonify({"player": player_profile(row)}), 200


# Logout: non elimina sessioni perché qui non sono gestite sessioni.
def logout():
    return "", 204

# ======================================================================
# ESEMPI: CHIAMATE DA app.py E RISULTATI
# ======================================================================
# register_player({
#     "email": "mario@example.com", "password": "password1234",
#     "nickname": "Mario", "avatar": "ranger", "bio": "Ciao!"
# })
# -> se tutto va bene: risposta JSON con "player" e codice HTTP 201.
#
# login({"email": "mario@example.com", "password": "password1234"})
# -> cerca con Database.fetch_one(...) e restituisce 200 oppure 401.
#
# logout()
# -> restituisce una risposta vuota con codice HTTP 204.