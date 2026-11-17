"""Logica di lettura, modifica e cancellazione dei profili dei giocatori."""

import logging

import requests

if __package__ == "component":
    from database import Database
else:
    from ..database import Database

from .exceptions import ConflictError, DependencyError, NotFoundError, StorageError, ValidationError
from .services import COLLECTOR_URL, ENCOUNTER_URL, GAME_MANAGER_URL, internal_request

logger = logging.getLogger(__name__)


# il parametro player_id è già stato estratto dall'URL da app.py.
def get_player(player_id):
    with Database() as db:
        row = db.fetch_one("SELECT * FROM players WHERE player_id = ?", (player_id,))
    if row is None:
        raise NotFoundError("not_found", "Player not found")
    # restituiamo un dizionario; la scelta dei campi da mostrare spetta ad app.py.
    return dict(row)


# aggiorna i tre campi del profilo e recupera i dati aggiornati.
def update_player(player_id, body):
    nickname = body.get("nickname")
    avatar = body.get("avatar")
    bio = body.get("bio")

    # la PUT richiede tutti e tre i campi, anche se un valore non cambia.
    if (
        not isinstance(nickname, str)
        or not nickname.strip()
        or len(nickname.strip()) > 32
        or not isinstance(avatar, str)
        or len(avatar) > 40
        or not isinstance(bio, str)
        or len(bio) > 500
    ):
        raise ValidationError("invalid_profile", "Profile details are invalid")

    # update e select usano la stessa transazione: commit solo quando entrambe riescono.
    try:
        with Database() as db:
            db.execute(
                "UPDATE players SET nickname = ?, avatar = ?, bio = ? WHERE player_id = ?",
                (nickname.strip(), avatar, bio.strip(), player_id),
            )
            row = db.fetch_one("SELECT * FROM players WHERE player_id = ?", (player_id,))
    except Database.IntegrityError as exc:
        if "UNIQUE constraint failed" in str(exc):
            raise ConflictError("nickname_taken", "That nickname is already in use") from exc
        logger.exception("Could not update player profile")
        raise StorageError("storage_error", "The profile could not be saved") from exc
    except Database.Error as exc:
        logger.exception("Could not update player profile")
        raise StorageError("storage_error", "The profile could not be saved") from exc

    if row is None:
        raise NotFoundError("not_found", "Player not found")
    return dict(row)


# per eliminare un player vanno rimossi anche i suoi dati negli altri microservizi.
def delete_player(player_id):
    # select 1 è sufficiente: ci serve soltanto sapere se l'id esiste.
    with Database() as db:
        existing = db.fetch_one("SELECT 1 FROM players WHERE player_id = ?", (player_id,))
    if existing is None:
        raise NotFoundError("not_found", "Player not found")

    failures = []
    for service_url, path in (
        (COLLECTOR_URL, f"/internal/players/{player_id}/collection"),
        (ENCOUNTER_URL, f"/internal/players/{player_id}/encounters"),
        (GAME_MANAGER_URL, f"/internal/players/{player_id}/battles"),
    ):
        try:
            # i DELETE vengono inviati direttamente ai servizi, non al nostro database.
            response = internal_request("DELETE", f"{service_url}{path}")
            # anche 404 è accettato: significa che lì i dati erano già assenti.
            if response.status_code not in (200, 204, 404):
                logger.error("Account cleanup failed for %s: %s", service_url, response.status_code)
                failures.append(service_url)
        except requests.RequestException:
            # un timeout non ci dice con certezza se la cancellazione sia avvenuta.
            logger.exception("Account cleanup request failed for %s", service_url)
            failures.append(service_url)

    if failures:
        # se almeno un servizio fallisce, non eliminiamo il player locale.
        # il client può riprovare la DELETE; i servizi già puliti accettano anche il 404.
        raise DependencyError(
            "cleanup_incomplete",
            "Some game data could not be removed. Retry account deletion to finish cleanup.",
        )

    # tutti i servizi hanno confermato: ora possiamo eliminare il player locale.
    with Database() as db:
        db.execute("DELETE FROM players WHERE player_id = ?", (player_id,))
    # non prepariamo la risposta http: app.py restituirà 204 senza contenuto.