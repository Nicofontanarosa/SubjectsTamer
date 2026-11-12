import json
import logging
from datetime import datetime

from flask import Flask, jsonify, request

from common.game import (
    add_stats,
    error_response,
    internal_required,
    load_catalog,
    require_player_access,
)
from common.storage import connect

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
CATALOG, MONSTERS = load_catalog()


def initialize_database():
    with connect("encounters.sqlite") as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS encounters (
                battle_id TEXT PRIMARY KEY,
                player_id TEXT NOT NULL,
                boss_id TEXT NOT NULL,
                team_json TEXT NOT NULL,
                result TEXT NOT NULL CHECK(result IN ('win', 'loss')),
                outcome TEXT NOT NULL,
                turns INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS encounter_player_date
                ON encounters(player_id, completed_at DESC);
            """
        )


def valid_timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def encounter_payload(row):
    team_ids = json.loads(row["team_json"])
    return {
        "battleId": row["battle_id"],
        "boss": add_stats(MONSTERS[row["boss_id"]]),
        "teamUsed": [add_stats(MONSTERS[monster_id]) for monster_id in team_ids],
        "result": row["result"],
        "outcome": row["outcome"],
        "turns": row["turns"],
        "startedAt": row["started_at"],
        "completedAt": row["completed_at"],
    }


@app.post("/internal/encounters")
@internal_required
def record_encounter():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response("invalid_request", "A JSON object is required", 400)
    battle_id = body.get("battleId")
    player_id = body.get("playerId")
    boss_id = body.get("bossId")
    team_ids = body.get("teamUsed")
    result = body.get("result")
    outcome = body.get("outcome", result)
    turns = body.get("turns")
    completed_at = body.get("timestamp")
    started_at = body.get("startedAt", completed_at)
    if not isinstance(battle_id, str) or not battle_id or len(battle_id) > 80:
        return error_response("invalid_battle", "A battle identifier is required", 400)
    if not isinstance(player_id, str) or not player_id:
        return error_response("invalid_player", "A player identifier is required", 400)
    if boss_id not in MONSTERS:
        return error_response("invalid_boss", "The boss must belong to the card catalog", 400)
    if (
        not isinstance(team_ids, list)
        or len(team_ids) != 3
        or any(not isinstance(monster_id, str) or monster_id not in MONSTERS for monster_id in team_ids)
        or len(set(team_ids)) != 3
    ):
        return error_response("invalid_team", "History requires three distinct catalog cards", 400)
    if result not in ("win", "loss") or not isinstance(outcome, str) or len(outcome) > 40:
        return error_response("invalid_result", "Result must be win or loss", 400)
    if not isinstance(turns, int) or isinstance(turns, bool) or turns < 0:
        return error_response("invalid_turns", "Turn count must be a non-negative integer", 400)
    if not valid_timestamp(completed_at) or not valid_timestamp(started_at):
        return error_response("invalid_timestamp", "Valid start and completion timestamps are required", 400)

    encoded_team = json.dumps(team_ids, separators=(",", ":"))
    with connect("encounters.sqlite") as db:
        existing = db.execute(
            "SELECT * FROM encounters WHERE battle_id = ?", (battle_id,)
        ).fetchone()
        if existing:
            same_encounter = (
                existing["player_id"] == player_id
                and existing["boss_id"] == boss_id
                and existing["team_json"] == encoded_team
                and existing["result"] == result
                and existing["outcome"] == outcome
                and existing["turns"] == turns
                and existing["started_at"] == started_at
                and existing["completed_at"] == completed_at
            )
            if not same_encounter:
                return error_response("battle_id_conflict", "This battle ID belongs to another result", 409)
            return jsonify({"encounter": encounter_payload(existing), "duplicate": True}), 200
        db.execute(
            """INSERT INTO encounters
               (battle_id, player_id, boss_id, team_json, result, outcome, turns, started_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                battle_id,
                player_id,
                boss_id,
                encoded_team,
                result,
                outcome,
                turns,
                started_at,
                completed_at,
            ),
        )
        row = db.execute(
            "SELECT * FROM encounters WHERE battle_id = ?", (battle_id,)
        ).fetchone()
    return jsonify({"encounter": encounter_payload(row), "duplicate": False}), 201


@app.get("/players/<player_id>/encounters")
def get_encounters(player_id):
    denial = require_player_access(player_id)
    if denial:
        return denial
    try:
        limit = int(request.args.get("limit", "20"))
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        return error_response("invalid_pagination", "Limit and offset must be integers", 400)
    if not 1 <= limit <= 100 or offset < 0:
        return error_response("invalid_pagination", "Limit must be 1-100 and offset cannot be negative", 400)
    with connect("encounters.sqlite") as db:
        total = db.execute(
            "SELECT COUNT(*) AS count FROM encounters WHERE player_id = ?", (player_id,)
        ).fetchone()["count"]
        rows = db.execute(
            """SELECT * FROM encounters WHERE player_id = ?
               ORDER BY completed_at DESC, battle_id DESC LIMIT ? OFFSET ?""",
            (player_id, limit, offset),
        ).fetchall()
    return jsonify(
        {
            "encounters": [encounter_payload(row) for row in rows],
            "pagination": {"limit": limit, "offset": offset, "total": total},
        }
    ), 200


@app.delete("/internal/players/<player_id>/encounters")
@internal_required
def delete_encounters(player_id):
    with connect("encounters.sqlite") as db:
        db.execute("DELETE FROM encounters WHERE player_id = ?", (player_id,))
    return "", 204


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "encounter"}), 200


initialize_database()
