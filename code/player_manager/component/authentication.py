"""Logica di registrazione e login dei giocatori, senza dipendenze da Flask."""

import logging
import re
import uuid
from datetime import datetime, timezone

import requests
from werkzeug.security import check_password_hash, generate_password_hash

# supportiamo sia l'avvio con gunicorn (package component) sia l'import del package completo.
if __package__ == "component":
    from database import Database
else:
    from ..database import Database

from .exceptions import AuthenticationError, ConflictError, DependencyError, StorageError, ValidationError
from .services import COLLECTOR_URL, internal_request

logger = logging.getLogger(__name__)


# riceve da app.py un normale dizionario con i dati del nuovo giocatore.
# controlla i valori, scrive nel database e chiede a collector la collezione iniziale.
def register_player(body):
    # get non genera errori se manca un campo; avatar e bio hanno valori predefiniti.
    email = body.get("email")
    password = body.get("password")
    nickname = body.get("nickname")
    avatar = body.get("avatar", "ranger")
    bio = body.get("bio", "")

    # qui controlliamo le regole della registrazione, non il formato della risposta http.
    if not isinstance(email, str) or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()):
        raise ValidationError("invalid_email", "Enter a valid email address")
    if not isinstance(password, str) or len(password) < 10:
        raise ValidationError("weak_password", "Password must contain at least 10 characters")
    if not isinstance(nickname, str) or not nickname.strip() or len(nickname.strip()) > 32:
        raise ValidationError("invalid_nickname", "Nickname must contain 1 to 32 characters")
    if not isinstance(avatar, str) or len(avatar) > 40 or not isinstance(bio, str) or len(bio) > 500:
        raise ValidationError("invalid_profile", "Avatar or biography is too long")

    # uuid identifica il player; la data viene salvata in UTC.
    player_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()

    # il with gestisce commit/rollback e chiusura della connessione sqlite.
    try:
        with Database() as db:
            db.execute(
                """INSERT INTO players
                   (player_id, email, password_hash, nickname, avatar, bio, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    player_id,
                    email.strip().lower(),
                    generate_password_hash(password),  # salviamo l'hash, non la password in chiaro.
                    nickname.strip(),
                    avatar,
                    bio.strip(),
                    created_at,
                ),
            )
    except Database.IntegrityError as exc:
        # sqlite impedisce email e nickname duplicati tramite i vincoli UNIQUE.
        if "UNIQUE constraint failed" in str(exc):
            raise ConflictError("account_exists", "Email or nickname is already in use") from exc
        logger.exception("Could not create player account")
        raise StorageError("storage_error", "The account could not be created") from exc
    except Database.Error as exc:
        logger.exception("Could not create player account")
        raise StorageError("storage_error", "The account could not be created") from exc

    # il player è già stato salvato; ora chiediamo a collector di inizializzare la collezione.
    # questa richiesta va direttamente all'altro microservizio, senza passare dal gateway.
    try:
        response = internal_request(
            "POST",
            f"{COLLECTOR_URL}/internal/players/{player_id}/collection/initialize",
        )
        if response.status_code not in (200, 201):
            logger.error("Collector initialization failed: %s", response.status_code)
            # manteniamo il comportamento attuale: eliminiamo il player locale se collector
            # non conferma il successo. un 5xx, però, non garantisce che non abbia già salvato i dati.
            with Database() as db:
                db.execute("DELETE FROM players WHERE player_id = ?", (player_id,))
            raise DependencyError("initialization_failed", "The starting collection could not be created")
    except requests.RequestException as exc:
        logger.exception("Collector could not be reached during registration")
        # con un timeout non sappiamo se collector abbia ricevuto la POST: il DELETE locale
        # potrebbe lasciare una collezione orfana. per ora conserviamo la logica precedente.
        with Database() as db:
            db.execute("DELETE FROM players WHERE player_id = ?", (player_id,))
        raise DependencyError("service_unavailable", "The collection service is unavailable") from exc

    # restituiamo i dati python ad app.py, che li trasformerà in una risposta HTTP.
    with Database() as db:
        row = db.fetch_one("SELECT * FROM players WHERE player_id = ?", (player_id,))
    return dict(row)


# legge il giocatore tramite email e verifica che la password corrisponda all'hash salvato.
def login(body):
    email, password = body.get("email"), body.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        raise AuthenticationError("invalid_credentials", "Email or password is incorrect")

    with Database() as db:
        row = db.fetch_one(
            "SELECT * FROM players WHERE email = ?",
            (email.strip().lower(),),
        )

    # il controllo row is None evita di accedere a una riga che non esiste.
    if row is None or not check_password_hash(row["password_hash"], password):
        raise AuthenticationError("invalid_credentials", "Email or password is incorrect")
    return dict(row)