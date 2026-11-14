import logging
import os
import random
import threading
import uuid
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, jsonify, request

from common.game import (
    add_stats,
    error_response,
    load_catalog,
)

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
COLLECTOR_URL = os.environ.get("COLLECTOR_URL", "http://collector:5005").rstrip("/")
ENCOUNTER_URL = os.environ.get("ENCOUNTER_URL", "http://encounter:5005").rstrip("/")
BATTLE_TTL_MINUTES = int(os.environ.get("BATTLE_TTL_MINUTES", "30"))
CATALOG, MONSTERS = load_catalog()
BATTLES = {}
PLAYER_BATTLES = {}
BATTLE_LOCK = threading.RLock()


def client_error(error, message, status):
    return error_response(error, message, status)


def player_id_from_request(body):
    player_id = body.get("playerId") if isinstance(body, dict) else None
    return player_id if isinstance(player_id, str) and player_id else None


def living_team(battle):
    return [member for member in battle["team"] if member["currentHp"] > 0]


def type_matchup(attacker_department, defender_department):
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
    battle["events"].append({"turn": battle["turns"], "text": text})
    battle["events"] = battle["events"][-24:]
    battle["latestEvent"] = text


def strike(attacker, defender, *, is_boss):
    attack_multiplier, defense_multiplier = type_matchup(
        attacker["department"], defender["department"]
    )
    attack_stat = attacker["battleStats"]["attack"] if is_boss else attacker["stats"]["attack"]
    defense_stat = defender["battleStats"]["defense"] if "battleStats" in defender else defender["stats"]["defense"]
    if is_boss:
        power = random.uniform(0.46, 0.62)
        mitigation = 0.25
    else:
        power = random.uniform(1.65, 1.95)
        mitigation = 0.38
    damage = max(6, round(attack_stat * power * attack_multiplier - defense_stat * mitigation * defense_multiplier))
    return damage, attack_multiplier > 1, defense_multiplier < 1


def public_battle(battle):
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
    expiry = datetime.now(timezone.utc) - timedelta(minutes=BATTLE_TTL_MINUTES)
    with BATTLE_LOCK:
        expired = [
            battle_id
            for battle_id, battle in BATTLES.items()
            if datetime.fromisoformat(battle["lastActivity"]) < expiry
        ]
        for battle_id in expired:
            battle = BATTLES.pop(battle_id)
            if PLAYER_BATTLES.get(battle["playerId"]) == battle_id:
                PLAYER_BATTLES.pop(battle["playerId"], None)


def boss_turn(battle):
    targets = living_team(battle)
    if not targets:
        battle["status"] = "lost"
        battle["result"] = "loss"
        battle["outcome"] = "defeat"
        return
    target = random.choice(targets)
    damage, advantaged, weakened = strike(battle["boss"], target, is_boss=True)
    target["currentHp"] = max(0, target["currentHp"] - damage)
    battle["turns"] += 1
    detail = f"{battle['boss']['name']} struck {target['name']} for {damage} damage"
    if advantaged:
        detail += " with a department advantage"
    if target["currentHp"] == 0:
        detail += "; the ally was knocked out"
    append_event(battle, detail + ".")
    if not living_team(battle):
        battle["status"] = "lost"
        battle["result"] = "loss"
        battle["outcome"] = "defeat"


def finalize_battle(battle):
    if battle["finalized"]:
        return None
    if battle["completedAt"] is None:
        battle["completedAt"] = datetime.now(timezone.utc).isoformat()
    if battle["result"] == "win":
        try:
            response = requests.post(
                f"{COLLECTOR_URL}/internal/players/{battle['playerId']}/collection/monsters",
                json={"monsterId": battle["boss"]["id"]},
                timeout=5,
            )
        except requests.RequestException:
            app.logger.exception("Collector could not record the encounter reward")
            return error_response("reward_unavailable", "The reward could not be saved; retry the action", 502)
        if response.status_code not in (200, 201):
            app.logger.error("Collector rejected the encounter reward: %s", response.status_code)
            return error_response("reward_unavailable", "The reward could not be saved; retry the action", 502)
        battle["reward"] = add_stats(MONSTERS[battle["boss"]["id"]])

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

    battle["finalized"] = True
    for member in battle["team"]:
        member["currentHp"] = member["stats"]["hp"]
    battle["activeTurn"] = "complete"
    if PLAYER_BATTLES.get(battle["playerId"]) == battle["battleId"]:
        PLAYER_BATTLES.pop(battle["playerId"], None)
    if battle["result"] == "win":
        append_event(battle, f"{battle['boss']['name']} joined your collection. Your team is restored.")
    elif battle["outcome"] == "abandoned":
        append_event(battle, "The encounter was abandoned. Your team is restored.")
    else:
        append_event(battle, "The encounter is over. Your team is restored.")
    return None


def make_boss(monster):
    boss = add_stats(monster)
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
    battle["lastActivity"] = datetime.now(timezone.utc).isoformat()


@app.post("/battles")
def start_battle():
    body = request.get_json(silent=True)
    player_id = player_id_from_request(body)
    if player_id is None:
        return client_error("invalid_player", "A player ID is required to start a battle", 400)
    cleanup_expired()
    with BATTLE_LOCK:
        active_id = PLAYER_BATTLES.get(player_id)
        if active_id and active_id in BATTLES and not BATTLES[active_id]["finalized"]:
            battle = BATTLES[active_id]
            touch(battle)
            return jsonify(public_battle(battle)), 200
        try:
            response = requests.get(
                f"{COLLECTOR_URL}/internal/players/{player_id}/team",
                timeout=5,
            )
        except requests.RequestException:
            app.logger.exception("Collector could not provide the active team")
            return client_error("team_unavailable", "The active team could not be loaded", 502)
        if response.status_code != 200:
            return client_error("team_unavailable", "A valid three-card team is required", 409)
        try:
            team_data = response.json()
        except ValueError:
            app.logger.error("Collector returned invalid team data")
            return client_error("team_unavailable", "Collector returned an invalid response", 502)
        if (
            not isinstance(team_data, dict)
            or not isinstance(team_data.get("team"), list)
            or not isinstance(team_data.get("ownedIds"), list)
        ):
            return client_error("team_unavailable", "Collector returned an invalid response", 502)
        owned_ids = set(team_data.get("ownedIds", []))
        candidates = [monster for monster in CATALOG if monster["id"] not in owned_ids]
        if not candidates:
            return client_error("graduated", "You have collected every available subject", 409)
        boss_source = random.choices(candidates, weights=[monster["cfu"] for monster in candidates], k=1)[0]
        team = []
        for monster in team_data["team"]:
            stats = monster["stats"]
            team.append({**monster, "currentHp": stats["hp"]})
        boss = make_boss(boss_source)
        battle_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc).isoformat()
        initiative = random.choice(("player", "boss"))
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
            "lastActivity": started_at,
            "finalized": False,
        }
        battle["events"].append({"turn": 0, "text": battle["latestEvent"]})
        BATTLES[battle_id] = battle
        PLAYER_BATTLES[player_id] = battle_id
        if initiative == "boss":
            boss_turn(battle)
            if battle["status"] == "lost":
                failure = finalize_battle(battle)
                if failure:
                    return failure
            else:
                battle["activeTurn"] = "player"
        touch(battle)
        return jsonify(public_battle(battle)), 201


@app.post("/battles/<battle_id>/actions")
def play_action(battle_id):
    body = request.get_json(silent=True)
    if (
        not isinstance(body, dict)
        or body.get("actionType") not in ("attack", "abandon")
        or (
            body.get("actionType") == "attack"
            and not isinstance(body.get("moveId"), str)
        )
    ):
        return client_error("invalid_action", "Use attack with a team card or abandon the encounter", 400)
    player_id = player_id_from_request(body)
    if player_id is None:
        return client_error("invalid_player", "A player ID is required for this action", 400)
    cleanup_expired()
    with BATTLE_LOCK:
        battle = BATTLES.get(battle_id)
        if battle is None:
            return client_error("battle_not_found", "This encounter has expired or does not exist", 404)
        if battle["playerId"] != player_id:
            return client_error("forbidden", "This encounter belongs to another player", 403)
        if battle["finalized"]:
            return jsonify(public_battle(battle)), 200
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
        if battle["status"] != "in_progress":
            failure = finalize_battle(battle)
            if failure:
                return failure
        return jsonify(public_battle(battle)), 200
        if battle["activeTurn"] != "player":
            return client_error("wrong_turn", "Wait for the boss turn to finish", 409)
        attacker = next(
            (
                member
                for member in battle["team"]
                if member["id"] == body["moveId"] and member["currentHp"] > 0
            ),
            None,
        )
        if attacker is None:
            return client_error("invalid_attacker", "Choose a living card from your active team", 400)
        damage, advantaged, weakened = strike(attacker, battle["boss"], is_boss=False)
        battle["boss"]["currentHp"] = max(0, battle["boss"]["currentHp"] - damage)
        battle["turns"] += 1
        detail = f"{attacker['name']} struck {battle['boss']['name']} for {damage} damage"
        if advantaged:
            detail += " with a department advantage"
        if weakened:
            detail += " through an exposed defense"
        append_event(battle, detail + ".")
        if battle["boss"]["currentHp"] == 0:
            battle["status"] = "won"
            battle["result"] = "win"
            battle["outcome"] = "victory"
        else:
            battle["activeTurn"] = "boss"
            boss_turn(battle)
            if battle["status"] == "in_progress":
                battle["activeTurn"] = "player"
        touch(battle)
        if battle["status"] != "in_progress":
            failure = finalize_battle(battle)
            if failure:
                return failure
            return jsonify(public_battle(battle)), 200

@app.delete("/internal/players/<player_id>/battles")
def delete_player_battles(player_id):
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
    cleanup_expired()
    with BATTLE_LOCK:
        return jsonify(
            {
                "status": "ok",
                "service": "game-manager",
                "activeBattles": sum(not battle["finalized"] for battle in BATTLES.values()),
            }
        ), 200
