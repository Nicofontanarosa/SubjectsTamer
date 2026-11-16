"""Player profile lookup, updates, and coordinated account deletion."""

# requests intercetta eventuali errori nei servizi contattati via HTTP.
import requests
from flask import current_app, jsonify

from common.game import error_response

# Consente gli import sia nell’avvio diretto sia come package.
if __package__ == "component":
    from database import Database
else:
    from ..database import Database

from .services import COLLECTOR_URL, ENCOUNTER_URL, GAME_MANAGER_URL, internal_request


# Converte una riga sqlite3.Row nel JSON pubblico, escludendo password_hash.
def player_profile(row):
    return {
        "playerId": row["player_id"],
        "email": row["email"],
        "nickname": row["nickname"],
        "avatar": row["avatar"],
        "bio": row["bio"],
        "createdAt": row["created_at"],
    }


# Cerca un player per ID. Se non esiste restituisce 404.
def get_player(player_id):
    with Database() as db:
        row = db.fetch_one("SELECT * FROM players WHERE player_id = ?", (player_id,))
        #fetch_one esgue la query e restituisce None se non trova il player; in tal caso restituisce errore 404.
    if row is None:
        return error_response("not_found", "Player not found", 404)
    return jsonify({"player": player_profile(row)}), 200


# Aggiorna nickname, avatar e bio ricevuti dal JSON.
def update_player(player_id, body):
    if not isinstance(body, dict):
        return error_response("invalid_request", "A JSON object is required", 400)
    # I tre campi sono obbligatori per questo aggiornamento PUT.
    nickname = body.get("nickname")
    avatar = body.get("avatar")
    bio = body.get("bio")
    # Valida tipo, presenza e lunghezza dei campi.
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
    # UPDATE e successiva SELECT usano la stessa connessione.
    try:
        with Database() as db:
            db.execute(
                "UPDATE players SET nickname = ?, avatar = ?, bio = ? WHERE player_id = ?",
                (nickname.strip(), avatar, bio.strip(), player_id),
            )
            row = db.fetch_one("SELECT * FROM players WHERE player_id = ?", (player_id,))
    # Se il nickname è già usato, il vincolo UNIQUE causa un errore 409.
    except Database.IntegrityError as exc:
        if "UNIQUE constraint failed" in str(exc):
            return error_response("nickname_taken", "That nickname is already in use", 409)
        current_app.logger.exception("Could not update player profile")# scrive il traceback nel log, ma non lo restituisce al client. lo scrive sul terminale o nel file di log configurato per l'app Flask. Questo aiuta a diagnosticare problemi senza esporre dettagli sensibili all'utente finale.
        return error_response("storage_error", "The profile could not be saved", 500)
    except Database.Error:
        current_app.logger.exception("Could not update player profile")
        return error_response("storage_error", "The profile could not be saved", 500)
    if row is None:
        return error_response("not_found", "Player not found", 404)
        # Se la SELECT non trova il player, significa che non esiste; restituisce errore 404.
    return jsonify({"player": player_profile(row)}), 200
    # Se tutto va bene, restituisce il profilo aggiornato con codice 200.


# Elimina prima i dati negli altri servizi, poi il profilo locale.
def delete_player(player_id):
    with Database() as db:
        existing = db.fetch_one("SELECT 1 FROM players WHERE player_id = ?", (player_id,))
        # fetch_one esegue la query e restituisce None se non trova il player; in tal caso restituisce errore 404.
    if existing is None:
        return error_response("not_found", "Player not found", 404)
    # Raccoglie i servizi che non hanno completato la cancellazione.
    failures = []
    for service_url, path in (
        (COLLECTOR_URL, f"/internal/players/{player_id}/collection"),
        (ENCOUNTER_URL, f"/internal/players/{player_id}/encounters"),
        (GAME_MANAGER_URL, f"/internal/players/{player_id}/battles"),
    ):
        try:
            # Invia una richiesta DELETE al servizio corrente.
            response = internal_request("DELETE", f"{service_url}{path}")
            if response.status_code not in (200, 204, 404): # se riceviamo 200 o 204, significa che il servizio ha cancellato correttamente i dati del player. Se riceviamo 404, significa che il player non esisteva già in quel servizio, quindi possiamo considerarlo come un successo per la cancellazione.
                # Se il servizio risponde con un errore, registra l’URL per il messaggio finale.
                current_app.logger.error(
                    "Account cleanup failed for %s: %s", service_url, response.status_code
                )
                failures.append(service_url)# aggiunge l’URL del servizio alla lista delle fallite, in modo da poter informare l’utente che alcuni dati non sono stati cancellati correttamente.
        except requests.RequestException:
            # Se la richiesta HTTP fallisce (timeout, connessione, ecc.), registra l’errore e aggiunge il servizio alla lista delle fallite. Perché non possiamo garantire che i dati siano stati cancellati, quindi dobbiamo informare l’utente che la cancellazione non è stata completata.
            current_app.logger.exception("Account cleanup request failed for %s", service_url)
            failures.append(service_url)
    # Se un servizio fallisce, mantiene il player e restituisce 502. Nel senso che se non riusciamo a cancellare i dati in tutti i servizi, non possiamo considerare l’account come completamente eliminato. Quindi informiamo l’utente che deve riprovare la cancellazione. 
    if failures:
        return error_response(
            "cleanup_incomplete",
            "Some game data could not be removed. Retry account deletion to finish cleanup.",
            502,
        )
    # Solo dopo aver contattato gli altri servizi rimuove il player dal DB.
    # è corretta senza mettere l'else perché abbiamo il return sopra.
    with Database() as db:
        db.execute("DELETE FROM players WHERE player_id = ?", (player_id,))
    return "", 204

# ======================================================================
# ESEMPI: CHIAMATE DA app.py
# ======================================================================
# get_player("123")
# -> SELECT per player_id; risposta JSON 200 oppure errore 404.
#
# update_player("123", {"nickname": "Mario", "avatar": "ranger", "bio": "Ciao"})
# -> UPDATE + SELECT nella stessa connessione; risposta 200 o errore.
#
# delete_player("123")
# -> DELETE HTTP verso Collector, Encounter e Game Manager;
#    poi DELETE SQL locale; risposta 204 oppure 404/502.
# Nota: i DELETE remoti non fanno parte della transazione SQLite.