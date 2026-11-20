# Moduli standard per log, configurazione, casualita', concorrenza e identificativi.
import logging
import os
import random
import threading
import uuid
from datetime import datetime, timedelta, timezone

# Librerie per le richieste HTTP e per l'API Flask.
import requests
from flask import Flask, jsonify, request

from common.game import (
    error_response,
    load_catalog,
)


#########################     Var       ######################################

# Inizializza il servizio Flask e imposta il livello dei log.
app = Flask(__name__)
app.logger.setLevel(logging.INFO)  # Imposta il livello dei log di Flask.

# Indirizzi dei servizi esterni e durata massima di inattivita' di una battaglia.
COLLECTOR_URL = os.environ.get("COLLECTOR_URL", "http://collector:5005").rstrip("/")
ENCOUNTER_URL = os.environ.get("ENCOUNTER_URL", "http://encounter:5005").rstrip("/")
BATTLE_TTL_MINUTES = int(os.environ.get("BATTLE_TTL_MINUTES", "30"))

# Carica il catalogo dei mostri e prepara gli archivi in memoria delle battaglie.
CATALOG, MONSTERS = load_catalog()
BATTLES = {}
PLAYER_BATTLES = {}
BATTLE_LOCK = threading.RLock()  # Evita modifiche concorrenti agli archivi in memoria.



############################       Func      #######################################
def error_response_wrapper(error, message, status):
    # Crea una risposta d'errore nel formato comune usato dagli altri servizi.
    return error_response(error, message, status)


def player_id_from_request(body):
    # Estrae playerId (solo se il corpo e' un dizionario e il valore e' una stringa non vuota).
    player_id = body.get("playerId") if isinstance(body, dict) else None
    return player_id if isinstance(player_id, str) and player_id else None


def alive_monster_in_team(battle):
    # Restituisce i membri della squadra con punti vita ancora maggiori di zero.
    return [member for member in battle["team"] if member["currentHp"] > 0]


def type_matchup_calculation(attacker_department, defender_department):
    # Imposta i moltiplicatori neutri; alcuni dipartimenti hanno vantaggio sugli altri.
    attack_multiplier = 1.0
    defense_multiplier = 1.0
    if attacker_department == "Computer Science" and defender_department == "Engineering":
        attack_multiplier = 1.2
        defense_multiplier = 0.8
    elif attacker_department == "Engineering" and defender_department == "Medicina e Chirurgia":
        attack_multiplier = 1.2
        defense_multiplier = 0.8
    elif attacker_department == "Medicina e Chirurgia" and defender_department == "Giurisprudenza":
        attack_multiplier = 1.2
        defense_multiplier = 0.8
    elif attacker_department == "Giurisprudenza" and defender_department == "Computer Science":
        attack_multiplier = 1.2
        defense_multiplier = 0.8
    return attack_multiplier, defense_multiplier


def append_event(battle, text):
    # Aggiunge un evento al turno corrente e conserva solo gli ultimi 24 eventi.
    battle["events"].append({"turn": battle["turns"], "text": text})
    battle["events"] = battle["events"][-24:]
    battle["latestEvent"] = text


def strike(attacker, defender, *, is_boss):
    # Calcola i modificatori di attacco e difesa in base ai dipartimenti dei contendenti.
    attack_multiplier, defense_multiplier = type_matchup_calculation(
        attacker["department"], defender["department"]
    )

    # Usa le statistiche da battaglia del boss e quelle normali degli alleati.
    attack_stat = attacker["battleStats"]["attack"] if is_boss else attacker["stats"]["attack"]
    defense_stat = defender["battleStats"]["defense"] if "battleStats" in defender else defender["stats"]["defense"]
   
    # Applica intervalli di potenza e mitigazione diversi per boss e alleati.
    if is_boss:
        power = random.uniform(0.46, 0.62)
        mitigation = 0.25
    else:
        power = random.uniform(1.65, 1.95)
        mitigation = 0.38
    # Il danno non puo' scendere sotto 6; restituisce anche i flag di vantaggio/svantaggio.
    damage = max(6, round(attack_stat * power * attack_multiplier - defense_stat * mitigation * defense_multiplier))
    return damage, attack_multiplier > 1, defense_multiplier < 1


def public_battle(battle):
    # Seleziona i soli dati della battaglia da esporre nelle risposte dell'API.
    return {
        "battleId": battle["battleId"],
        "playerId": battle["playerId"],
        "boss": battle["boss"],
        "team": battle["team"],
        "initiative": battle["initiative"],
        "activeTurn": battle["activeTurn"],
        "turns": battle["turns"],
        "status": battle["status"],
        "result": battle["result"],
        "outcome": battle["outcome"],
        "reward": battle["reward"],
        "events": battle["events"],
        "latestEvent": battle["latestEvent"],
        "startedAt": battle["startedAt"],
        "completedAt": battle["completedAt"],
        "finalized": battle["finalized"],
    }


def cleanup_expired():
    # Calcola la soglia temporale oltre la quale una battaglia e' considerata inattiva.
    expiry = datetime.now(timezone.utc) - timedelta(minutes=BATTLE_TTL_MINUTES)
    # Protegge gli archivi condivisi mentre individua e rimuove le battaglie scadute.
    with BATTLE_LOCK:
        expired = [
            battle_id
            for battle_id, battle in BATTLES.items()
            if datetime.fromisoformat(battle["lastActivityTime"]) < expiry
        ]
        for battle_id in expired:
            battle = BATTLES.pop(battle_id)
            # Rimuove il collegamento al giocatore solo se punta ancora a questa battaglia.
            if PLAYER_BATTLES.get(battle["playerId"]) == battle_id:
                PLAYER_BATTLES.pop(battle["playerId"], None)


def boss_turn(battle):
    # Il boss sceglie casualmente un alleato ancora in piedi come bersaglio.
    targets = alive_monster_in_team(battle)
    
    if not targets:
        # Se non ci sono bersagli vivi, la battaglia termina con una sconfitta.
        battle["status"] = "lost"
        battle["result"] = "loss"
        battle["outcome"] = "defeat"
        return
    
    target = random.choice(targets)
    # Calcola e applica il danno, senza permettere ai punti vita di scendere sotto zero.
    damage, advantaged, weakened = strike(battle["boss"], target, is_boss=True)
    target["currentHp"] = max(0, target["currentHp"] - damage)
    battle["turns"] += 1

    # Descrive l'attacco e aggiunge dettagli sul vantaggio e sull'eventuale KO.
    detail = f"{battle['boss']['name']} struck {target['name']} for {damage} damage"
    if advantaged:
        detail += " with a department advantage"
    if target["currentHp"] == 0:
        detail += "; the ally was knocked out"
    append_event(battle, detail + ".")

    # Se l'attacco ha messo KO tutta la squadra, registra la sconfitta.
    if not alive_monster_in_team(battle):
        battle["status"] = "lost"
        battle["result"] = "loss"
        battle["outcome"] = "defeat"


def finalize_battle(battle):
    # Evita di salvare due volte una battaglia gia' conclusa.
    if battle["finalized"]:
        return None
    
    # Registra l'ora di completamento una sola volta.
    if battle["completedAt"] is None:
        battle["completedAt"] = datetime.now(timezone.utc).isoformat()

    # In caso di vittoria, aggiunge il boss alla collezione del giocatore.
    if battle["result"] == "win":
        try:
            collector_response = requests.post(
                f"{COLLECTOR_URL}/internal/players/{battle['playerId']}/collection/monsters",
                json={"monsterId": battle["boss"]["id"]},
                timeout=5,
            )
        except requests.RequestException:
            app.logger.exception("Collector could not record the encounter reward")
            return error_response("reward_unavailable", "The reward could not be saved; retry the action", 502)
        if collector_response.status_code not in (200, 201):
            app.logger.error("Collector rejected the encounter reward: %s", collector_response.status_code)
            return error_response("reward_unavailable", "The reward could not be saved; retry the action", 502)
        battle["reward"] = dict(MONSTERS[battle["boss"]["id"]])

    # Prepara il riepilogo da inviare al servizio Encounter (che conserva la cronologia degli incontri).
    record = {
        "battleId": battle["battleId"],
        "playerId": battle["playerId"],
        "bossId": battle["boss"]["id"],
        "teamUsed": [member["id"] for member in battle["team"]],
        "result": battle["result"],
        "outcome": battle["outcome"],
        "turns": battle["turns"],
        "timestamp": battle["completedAt"],
        "startedAt": battle["startedAt"],
    }
    
    # Invia il risultato dell'incontro; se il servizio non e' disponibile, la battaglia rimane conclusa ma non finalizzata.
    try:
        response = requests.post(
            f"{ENCOUNTER_URL}/internal/encounters",
            json=record,
            timeout=5,
        )
    except requests.RequestException:
        app.logger.exception("Encounter service could not record the completed battle")
        return error_response("history_unavailable", "The result could not be saved; retry the action", 502)
    if response.status_code not in (200, 201):
        app.logger.error("Encounter service rejected the completed battle: %s", response.status_code)
        return error_response("history_unavailable", "The result could not be saved; retry the action", 502)

    # Se encounter risponde positivamente: Finalizza la battaglia, togliendola dalla lista delle battaglia aperte.
    battle["finalized"] = True
    for member in battle["team"]:
        member["currentHp"] = member["stats"]["hp"]
    battle["activeTurn"] = "complete"
    if PLAYER_BATTLES.get(battle["playerId"]) == battle["battleId"]:
        PLAYER_BATTLES.pop(battle["playerId"], None)
    
    # Aggiunge un messaggio finale coerente con vittoria, abbandono o altra conclusione.
    if battle["result"] == "win":
        append_event(battle, f"{battle['boss']['name']} joined your collection. Your team is restored.")
    elif battle["outcome"] == "abandoned":
        append_event(battle, "The encounter was abandoned. Your team is restored.")
    else:
        append_event(battle, "The encounter is over. Your team is restored.")
    return None


def make_boss(monster):
    # Copia le statistiche del mostro e le potenzia per adattarlo al ruolo di boss.
    boss = dict(monster)
    base_stats = boss["stats"]
    boss["normalStats"] = dict(base_stats)
    boss["battleStats"] = {
        key: max(1, round(value * 2.5)) for key, value in base_stats.items()
    }
    boss["stats"] = dict(boss["battleStats"])
    boss["isBoss"] = True
    boss["currentHp"] = boss["stats"]["hp"]
    return boss


def touch(battle):
    # Aggiorna il timestamp usato per calcolare la scadenza per inattivita'.
    battle["lastActivityTime"] = datetime.now(timezone.utc).isoformat()





############################      API      #######################################

@app.post("/battles") #ok
def start_battle():
    # Legge il JSON inviato dal client e verifica che contenga un ID giocatore valido.
    body = request.get_json(silent=True)
    player_id = player_id_from_request(body)
    if player_id is None:
        return error_response_wrapper("invalid_player", "A player ID is required to start a battle", 400)
    
    # Rimuove le battaglie inattive prima di cercarne o crearne una.
    cleanup_expired()

    # Serializza le modifiche allo stato condiviso delle battaglie.
    with BATTLE_LOCK:

        # Se esiste gia' una battaglia attiva, la riutilizza invece di crearne un'altra.
        active_id = PLAYER_BATTLES.get(player_id)
        if active_id and active_id in BATTLES and not BATTLES[active_id]["finalized"]:
            battle = BATTLES[active_id]
            touch(battle)
            return jsonify(public_battle(battle)), 200

        # Se non esiste una battaglia attiva, chiede al Collector la squadra selezionata.
        try:
            collector_response = requests.get(
                f"{COLLECTOR_URL}/internal/players/{player_id}/team",
                timeout=5,
            )
        except requests.RequestException:
            app.logger.exception("Collector could not provide the active team")
            return error_response_wrapper("team_unavailable", "The active team could not be loaded", 502)
        if collector_response.status_code != 200:
            return error_response_wrapper("team_unavailable", "A valid three-card team is required", 409)

        # Converte il corpo della risposta in JSON; se non e' valido, segnala un errore del Collector.
        try:
            monster_data = collector_response.json()
        except ValueError:
            app.logger.error("Collector returned invalid team data")
            return error_response_wrapper("team_unavailable", "Collector returned an invalid response", 502)
        
        # Verifica che la risposta abbia i campi e i tipi necessari per continuare.
        if (
            not isinstance(monster_data, dict)
            or not isinstance(monster_data.get("team"), list)
            or not isinstance(monster_data.get("ownedIds"), list)
        ):
            return error_response_wrapper("team_unavailable", "Collector returned an invalid response", 502)
        
        # Esclude i mostri gia' posseduti dal giocatore dai possibili boss.
        owned_ids = set(monster_data.get("ownedIds", []))
        candidates = [monster for monster in CATALOG if monster["id"] not in owned_ids]
        if not candidates:
            return error_response_wrapper("graduated", "You have collected every available subject", 409)
        
        # Estrae un boss tra quelli disponibili, dando piu' probabilita' ai mostri con piu' CFU.
        boss_source = random.choices(candidates, weights=[monster["cfu"] for monster in candidates], k=1)[0]
        
        # Copia la squadra ricevuta e inizializza i punti vita correnti al valore massimo.
        team = []
        for monster in monster_data["team"]:
            stats = monster["stats"]
            team.append({**monster, "currentHp": stats["hp"]})

        # Prepara il boss e i dati iniziali della battaglia.
        boss = make_boss(boss_source)
        battle_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc).isoformat()

        # Decide casualmente chi effettua la prima mossa.
        initiative = random.choice(("player", "boss"))

        # Crea lo stato iniziale completo della battaglia.
        battle = {
            "battleId": battle_id,
            "playerId": player_id,
            "boss": boss,
            "team": team,
            "initiative": initiative,
            "activeTurn": initiative,
            "turns": 0,
            "status": "in_progress",
            "result": None,
            "outcome": None,
            "reward": None,
            "events": [],
            "latestEvent": "The coin falls. You strike first." if initiative == "player" else "The coin falls. The boss strikes first.",
            "startedAt": started_at,
            "completedAt": None,
            "lastActivityTime": started_at,
            "finalized": False,
        }
        
        # Registra l'evento iniziale e associa la battaglia al giocatore.
        battle["events"].append({"turn": 0, "text": battle["latestEvent"]})
        BATTLES[battle_id] = battle
        PLAYER_BATTLES[player_id] = battle_id

        # Se il boss ha l'iniziativa, esegue subito il suo turno.
        if initiative == "boss":
            boss_turn(battle)
            if battle["status"] == "lost":
                # Finalizza subito una battaglia persa gia' al primo attacco del boss.
                failure = finalize_battle(battle)
                if failure:
                    return failure
            else:
                battle["activeTurn"] = "player"

        # Aggiorna l'ultima attivita' e restituisce la battaglia creata.
        touch(battle)
        return jsonify(public_battle(battle)), 201


@app.post("/battles/<battle_id>/actions")
def play_action(battle_id):
    # Controlla il formato dell'azione e richiede un moveId per gli attacchi.
    body = request.get_json(silent=True)
    if (
        not isinstance(body, dict)
        or body.get("actionType") not in ("attack", "abandon")
        or (
            body.get("actionType") == "attack"
            and not isinstance(body.get("moveId"), str)
        )
    ):
        return error_response_wrapper("invalid_action", "Use attack with a team card or abandon the encounter", 400)
   
    # L'ID del giocatore serve a verificare che possa agire su questa battaglia.
    player_id = player_id_from_request(body)
    if player_id is None:
        return error_response_wrapper("invalid_player", "A player ID is required for this action", 400)
   
    # Elimina le battaglie scadute 
    cleanup_expired()
    
    with BATTLE_LOCK:
        battle = BATTLES.get(battle_id)
        if battle is None:
            return error_response_wrapper("battle_not_found", "This encounter has expired or does not exist", 404)
        
        if battle["playerId"] != player_id:
            return error_response_wrapper("forbidden", "This encounter belongs to another player", 403)
       
        if battle["finalized"]:
            return jsonify(public_battle(battle)), 200

        # L'abbandono chiude una battaglia in corso e ne salva il risultato finale.
        if body["actionType"] == "abandon":
            if battle["status"] == "in_progress":
                battle["status"] = "lost"
                battle["result"] = "loss"
                battle["outcome"] = "abandoned"
                battle["activeTurn"] = "complete"
                touch(battle)
                append_event(battle, "You withdrew from the encounter.")
            failure = finalize_battle(battle)
            if failure:
                return failure
            return jsonify(public_battle(battle)), 200

        # Completa il salvataggio se la battaglia era completata ma non finalizzata.
        if battle["status"] != "in_progress": 
            failure = finalize_battle(battle)
            if failure:
                return failure
            return jsonify(public_battle(battle)), 200
       
        if battle["activeTurn"] != "player":
            return error_response_wrapper("wrong_turn", "Wait for the boss turn to finish", 409)
       
        # Cerca nella squadra la carta scelta, che deve essere ancora viva.
        attacker = next(
            (
                member
                for member in battle["team"]
                if member["id"] == body["moveId"] and member["currentHp"] > 0
            ),
            None,
        )
        if attacker is None:
            return error_response_wrapper("invalid_attacker", "Choose a living card from your active team", 400)
        
        # Applica l'attacco al boss e registra il danno nel riepilogo degli eventi.
        damage, advantaged, weakened = strike(attacker, battle["boss"], is_boss=False)
        battle["boss"]["currentHp"] = max(0, battle["boss"]["currentHp"] - damage)
        battle["turns"] += 1
        detail = f"{attacker['name']} struck {battle['boss']['name']} for {damage} damage"
        if advantaged:
            detail += " with a department advantage"
        if weakened:
            detail += " through an exposed defense"
        append_event(battle, detail + ".")

        #controllo vita boss
        if battle["boss"]["currentHp"] == 0:
            battle["status"] = "won"
            battle["result"] = "win"
            battle["outcome"] = "victory"
        else:
            # Se il boss e' ancora vivo, gli fa eseguire il contrattacco.
            battle["activeTurn"] = "boss"
            boss_turn(battle)
            if battle["status"] == "in_progress":
                battle["activeTurn"] = "player"
        touch(battle)
       
        if battle["status"] != "in_progress":
            # Registra ricompensa e cronologia quando la battaglia raggiunge uno stato finale.
            failure = finalize_battle(battle)
            if failure:
                return failure
        return jsonify(public_battle(battle)), 200


@app.delete("/internal/players/<player_id>/battles")
def delete_player_battles(player_id):
    # Rimuove tutte le battaglie del giocatore e il relativo indice delle battaglie attive.
    with BATTLE_LOCK:
        battle_ids = [
            battle_id
            for battle_id, battle in BATTLES.items()
            if battle["playerId"] == player_id
        ]
        for battle_id in battle_ids:
            BATTLES.pop(battle_id, None)
        PLAYER_BATTLES.pop(player_id, None)
    return "", 204


@app.get("/health")
def health():
    # Rimuove prima gli incontri scaduti e poi restituisce lo stato del servizio.
    cleanup_expired()
    with BATTLE_LOCK:
        return jsonify(
            {
                "status": "ok",
                "service": "game-manager",
                "activeBattles": sum(not battle["finalized"] for battle in BATTLES.values()),
            }
        ), 200
