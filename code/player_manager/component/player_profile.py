"""Player profile lookup, updates, and coordinated account deletion."""

# requests serve per gestire eventuali errori nelle cancellazioni sugli altri servizi.
import requests
from flask import current_app, jsonify

from common.game import error_response

# anche qui il percorso dell'import cambia in base a come si avvia il servizio.
if __package__ == "component":
    from database import Database
else:
    from ..database import Database

# qui importiamo gli indirizzi degli altri servizi e il metodo per chiamarli.
from .services import COLLECTOR_URL, ENCOUNTER_URL, GAME_MANAGER_URL, internal_request


# la riga letta dal db non è ancora il json che vogliamo mandare al frontend.
# qui decidiamo quali dati restituire e come chiamare i camipi.
def player_profile(row):
    return {
        "playerId": row["player_id"],
        "email": row["email"],
        "nickname": row["nickname"],
        "avatar": row["avatar"],
        "bio": row["bio"],
        "createdAt": row["created_at"],
    }


# per leggere un player, il suo id arriva dal percorso dell'url e non dal body.
def get_player(player_id):
    with Database() as db:
        row = db.fetch_one("SELECT * FROM players WHERE player_id = ?", (player_id,))
    # fetch_one restituisce una riga (sqlite3.row) oppure none.
    if row is None:
        return error_response("not_found", "Player not found", 404)
    return jsonify({"player": player_profile(row)}), 200


# questa funzione modifica il profilo indicato nell'url.
def update_player(player_id, body):
    # app.py ha gia letto il json; se body non è un dizionario torniamo 400.
    if not isinstance(body, dict):
        return error_response("invalid_request", "A JSON object is required", 400)

    # per fare la modifica chiediamo tutti e tre i campi, anche se uno non cambia.
    nickname = body.get("nickname")
    avatar = body.get("avatar")
    bio = body.get("bio")
    # nickname non può essere vuoto; avatar e bio possono esserlo, ma sono limitati.
    if (
        not isinstance(nickname, str)
        or not nickname.strip()
        or len(nickname.strip()) > 32
        or not isinstance(avatar, str)
        or len(avatar) > 40
        or not isinstance(bio, str)
        or len(bio) > 500
    ):
        return error_response("invalid_profile", "Profile details are invalid", 400)

    # update e select vengono eseguite usando la stessa connessione sqlite.
    # il with salva solo quando entrambe le operazioni terminano senza errori.
    try:
        with Database() as db:
            db.execute(
                "UPDATE players SET nickname = ?, avatar = ?, bio = ? WHERE player_id = ?",
                (nickname.strip(), avatar, bio.strip(), player_id),
            )
            row = db.fetch_one("SELECT * FROM players WHERE player_id = ?", (player_id,))
    # il vincolo unique evita che due player abbiano lo stesso nickname.
    except Database.IntegrityError as exc:
        if "UNIQUE constraint failed" in str(exc):
            return error_response("nickname_taken", "That nickname is already in use", 409)
        current_app.logger.exception("Could not update player profile")
        return error_response("storage_error", "The profile could not be saved", 500)
    except Database.Error:
        # l'errore viene salvato nei log ma non mandato al client.
        current_app.logger.exception("Could not update player profile")
        return error_response("storage_error", "The profile could not be saved", 500)

    # se l'id non esiste, update non modifica nulla e anche select trova none.
    if row is None:
        return error_response("not_found", "Player not found", 404)
    return jsonify({"player": player_profile(row)}), 200


# quando eliminiamo un player dobbiamo togliere anche i suoi dati dagli altri servizi.
def delete_player(player_id):
    # qui facciamo select 1 perchè ci interessa solo sapere se il player esiste.
    with Database() as db:
        existing = db.fetch_one("SELECT 1 FROM players WHERE player_id = ?", (player_id,))
    if existing is None:
        return error_response("not_found", "Player not found", 404)

    # in questa lista mettiamo i servizi che non hanno cancellato correttamente.
    failures = []
    for service_url, path in (
        (COLLECTOR_URL, f"/internal/players/{player_id}/collection"),
        (ENCOUNTER_URL, f"/internal/players/{player_id}/encounters"),
        (GAME_MANAGER_URL, f"/internal/players/{player_id}/battles"),
    ):
        try:
            # questa è una chiamata http agli altri servizi, non una query al nostro db.
            response = internal_request("DELETE", f"{service_url}{path}")
            # 200/204 = operazione riuscita; 404 = dati già assenti in quel servizio.
            if response.status_code not in (200, 204, 404):
                current_app.logger.error(
                    "Account cleanup failed for %s: %s", service_url, response.status_code
                )
                failures.append(service_url)
        except requests.RequestException:
            # timeout o servizio non raggiungibile: non sappiamo se abbia eliminato i dati.
            current_app.logger.exception("Account cleanup request failed for %s", service_url)
            failures.append(service_url)

    # se almeno un servizio fallisce, per ora non eliminiamo il profilo locale.
    # in questo modo, dal frontend, il giocatore può inivaire una nuova delete e riprovare a cancellare i dati rimasti negli altri servizi
    # infatti il profi lo locale non viene eliminato finchè tutti i servizi non confermano la cancellazione. pensato per poter essere ripetuto più volte senza perdere dati.
    # questo non annulla eventuali delete già riuscite negli altri servizi.
    if failures:
        return error_response(
            "cleanup_incomplete",
            "Some game data could not be removed. Retry account deletion to finish cleanup.",
            502,
        )
    # se siamo arrivati qui, tutte le risposte remote sono state accettate.
    with Database() as db:
        db.execute("DELETE FROM players WHERE player_id = ?", (player_id,))
    # stesso return della funzione logout: 204 = nessun contenuto, ma la richiesta è stata completata con successo.
    return "", 204