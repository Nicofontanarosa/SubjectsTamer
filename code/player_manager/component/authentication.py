"""Registration, login, and logout operations."""

# queste librerie servono per controllare la mail, creare un id e salvare la data.
import re
import uuid
from datetime import datetime, timezone

# requests ci serve per intercettare problemi nelle chiamate agli altri servizi.
import requests
from flask import current_app, jsonify
# werkzeug ci permette di salvare un hash e controllarlo quando si fa login.
from werkzeug.security import check_password_hash, generate_password_hash

# funzione comune che prepara una risposta json di errore.
from common.game import error_response

# questi due casi dipendono da come viene avviato app.py.
# in docker si usa il primo import, come package invece quello relativo.
if __package__ == "component":
    from database import Database
else:
    from ..database import Database

from .player_profile import player_profile
from .services import COLLECTOR_URL, internal_request


# questa funzione viene chiamata da app.py quando arriva una registrazione.
# body contiene i dati json che il frontend ha inviato.
# il giro completo della richiesta è spiegato in fondo, punto [a].
def register_player(body):
    # se body non è un dizionario, i dati non vanno bene e ritorniamo 400.
    if not isinstance(body, dict):
        return error_response("invalid_request", "A JSON object is required", 400)

    # con get recupero i campi; se manca avatar o bio uso i valori di default.
    email = body.get("email")
    password = body.get("password")
    nickname = body.get("nickname")
    avatar = body.get("avatar", "ranger")
    bio = body.get("bio", "")

    # prima di inserire nel db controlliamo che i dati siano corretti.
    # fullmatch controlla l'intera stringa; questa regex verifica un formato base.
    if not isinstance(email, str) or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()):
        return error_response("invalid_email", "Enter a valid email address", 400)
    if not isinstance(password, str) or len(password) < 10:
        return error_response("weak_password", "Password must contain at least 10 characters", 400)
    if not isinstance(nickname, str) or not nickname.strip() or len(nickname.strip()) > 32:
        return error_response("invalid_nickname", "Nickname must contain 1 to 32 characters", 400)
    if not isinstance(avatar, str) or len(avatar) > 40 or not isinstance(bio, str) or len(bio) > 500:
        return error_response("invalid_profile", "Avatar or biography is too long", 400)

    # generiamo un id casuale e la data di registrazione con fuso orario utc.
    player_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    # il with apre il collegamento al db e lo chiude dopo la query.
    try:
        with Database() as db:
            db.execute(
                """INSERT INTO players
                   (player_id, email, password_hash, nickname, avatar, bio, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    player_id,
                    email.strip().lower(),
                    generate_password_hash(password),  # nel db salvo l'hash, non la password originale.
                    nickname.strip(),
                    avatar,
                    bio.strip(),
                    created_at,
                ),
            )
        # se email o nickname sono già utilizzati, il vincolo UNIQUE impedisce
        # l'inserimento. sqlite solleva un IntegrityError che intercettiamo qui.    
    except Database.IntegrityError as exc:
        if "UNIQUE constraint failed" in str(exc):
            return error_response("account_exists", "Email or nickname is already in use", 409)
        current_app.logger.exception("Could not create player account")
        return error_response("storage_error", "The account could not be created", 500)
    except Database.Error:
        # altri errori sqlite (per esempio db bloccato o non scrivibile).
        current_app.logger.exception("Could not create player account")
        return error_response("storage_error", "The account could not be created", 500)

    # ora il player è salvato, ma va creata anche la sua collezione iniziale.
    # questa chiamata è diretta verso collector, senza passare dal gateway.
    try:
        # inviamo una richiesta POST a collector tramite internal_request.
        # nell'url passiamo il player_id appena creato, in modo che collector possa associargli le tre carte iniziali e la sua squadra.
        response = internal_request(
            "POST",
            f"{COLLECTOR_URL}/internal/players/{player_id}/collection/initialize",
        )
        if response.status_code not in (200, 201):
            # se collector risponde con uno stato diverso da 200 o 201, consideriamo
            # fallita l'inizializzazione. attenzione però: un errore 5xx non garantisce che collector non abbia già salvato la collezione nel proprio database. 
            current_app.logger.error("Collector initialization failed: %s", response.status_code)
            with Database() as db:
                # dato che collector non ha confermato l'inizializzazione,
                # eliminiamo il player dal nostro database per annullare la registrazione.
                db.execute("DELETE FROM players WHERE player_id = ?", (player_id,))
            return error_response("initialization_failed", "The starting collection could not be created", 502)
    except requests.RequestException:
        # qui intercettiamo gli errori di comunicazione, come un timeout oppure collector che non risponde. questi errori non sono risposte HTTP,
        current_app.logger.exception("Collector could not be reached during registration")
        # in questo caso non sappiamo se collector abbia creato la collezione, perché potrebbe aver salvato i dati senza riuscire a inviarci la risposta.
        # per ora eliminiamo comunque il player, ma questo potrebbe lasciare una collezione orfana nel database di collector.
        with Database() as db:
            db.execute("DELETE FROM players WHERE player_id = ?", (player_id,))
        return error_response("service_unavailable", "The collection service is unavailable", 502)

    # recuperiamo dal db i dati del player che abbiamo appena inserito.
    with Database() as db:
        row = db.fetch_one("SELECT * FROM players WHERE player_id = ?", (player_id,))
    # player_profile esclude password_hash dalla risposta; 201 = risorsa creata.
    return jsonify({"player": player_profile(row)}), 201


# qui arriviamo quando app.py riceve la richiesta di login.
def login(body):
    if not isinstance(body, dict):
        return error_response("invalid_request", "A JSON object is required", 400)
    email, password = body.get("email"), body.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        return error_response("invalid_credentials", "Email or password is incorrect", 401)

    # l'email viene normalizzata nello stesso modo usato in registrazione.
    with Database() as db:
        row = db.fetch_one(
            "SELECT * FROM players WHERE email = ?",
            (email.strip().lower(),),
        )
    # se non trovo il player non provo neanche a leggere row["password_hash"]. check_password_hash confronta la password ricevuta con l'hash nel db.
    if row is None or not check_password_hash(row["password_hash"], password):
        return error_response("invalid_credentials", "Email or password is incorrect", 401)
    return jsonify({"player": player_profile(row)}), 200


# per adesso logout ritorna solo 204, senza contenuto. qui non sono ancora gestite sessioni da terminare.
def logout():
    return "", 204
