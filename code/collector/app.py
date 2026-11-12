import logging
import random

from flask import Flask, jsonify, request, send_file
from pathlib import Path

from common.game import (
    add_stats,
    authenticated_player_id,
    error_response,
    internal_required,
    load_catalog,
    require_player_access,
)
from common.storage import connect

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
CATALOG, MONSTERS = load_catalog()
ASSET_DIR = Path("/app/assets")


def initialize_database():
    with connect("collection.sqlite") as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS collection (
                player_id TEXT NOT NULL,
                monster_id TEXT NOT NULL,
                acquired_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (player_id, monster_id)
            );
            CREATE TABLE IF NOT EXISTS teams (
                player_id TEXT PRIMARY KEY,
                slot_1 TEXT NOT NULL,
                slot_2 TEXT NOT NULL,
                slot_3 TEXT NOT NULL
            );
            """
        )


def owned_ids(db, player_id):
    rows = db.execute(
        "SELECT monster_id FROM collection WHERE player_id = ? ORDER BY acquired_at, monster_id",
        (player_id,),
    ).fetchall()
    return [row["monster_id"] for row in rows]


def saved_team(db, player_id):
    row = db.execute(
        "SELECT slot_1, slot_2, slot_3 FROM teams WHERE player_id = ?", (player_id,)
    ).fetchone()
    return list(row) if row else None


def monster_payload(monster_id, current_hp=None):
    payload = add_stats(MONSTERS[monster_id])
    if current_hp is not None:
        payload["currentHp"] = current_hp
    return payload


@app.post("/internal/players/<player_id>/collection/initialize")
@internal_required
def initialize_collection(player_id):
    candidates = [monster for monster in CATALOG if monster["cfu"] in (6, 9)]
    if len(candidates) < 3:
        return error_response("catalog_invalid", "At least three 6 or 9 CFU cards are required", 500)
    chosen = random.sample(candidates, 3)
    with connect("collection.sqlite") as db:
        existing = db.execute(
            "SELECT monster_id FROM collection WHERE player_id = ?", (player_id,)
        ).fetchall()
        if existing:
            return jsonify({"playerId": player_id, "monsterIds": [row["monster_id"] for row in existing]}), 200
        db.executemany(
            "INSERT INTO collection(player_id, monster_id) VALUES (?, ?)",
            [(player_id, monster["id"]) for monster in chosen],
        )
        db.execute(
            "INSERT INTO teams(player_id, slot_1, slot_2, slot_3) VALUES (?, ?, ?, ?)",
            (player_id, *(monster["id"] for monster in chosen)),
        )
    return jsonify({"playerId": player_id, "monsterIds": [monster["id"] for monster in chosen]}), 201


@app.get("/players/<player_id>/collection")
def get_collection(player_id):
    denial = require_player_access(player_id)
    if denial:
        return denial
    with connect("collection.sqlite") as db:
        ids = owned_ids(db, player_id)
        team_ids = saved_team(db, player_id)
    return jsonify(
        {
            "monsters": [monster_payload(monster_id) for monster_id in ids],
            "team": team_ids or [],
            "progress": {"owned": len(ids), "total": len(CATALOG)},
        }
    ), 200


@app.get("/monsters")
def get_catalog():
    player_id = authenticated_player_id()
    if player_id is None:
        return error_response("unauthorized", "Sign in to continue", 401)
    with connect("collection.sqlite") as db:
        owned = set(owned_ids(db, player_id))
    monsters = [{**monster_payload(monster["id"]), "owned": monster["id"] in owned} for monster in CATALOG]
    return jsonify({"monsters": monsters, "progress": {"owned": len(owned), "total": len(CATALOG)}}), 200


@app.get("/monsters/<monster_id>/image")
def get_monster_image(monster_id):
    monster = MONSTERS.get(monster_id)
    if monster is None:
        return error_response("not_found", "Card artwork not found", 404)
    image_path = ASSET_DIR / monster["image"]
    if not image_path.is_file():
        app.logger.error("Catalog image is missing for %s", monster_id)
        return error_response("image_unavailable", "Card artwork is unavailable", 500)
    return send_file(image_path, mimetype="image/jpeg", conditional=True, max_age=3600)


@app.put("/players/<player_id>/team")
def update_team(player_id):
    denial = require_player_access(player_id)
    if denial:
        return denial
    body = request.get_json(silent=True)
    monster_ids = body.get("monsterIds") if isinstance(body, dict) else None
    if (
        not isinstance(monster_ids, list)
        or len(monster_ids) != 3
        or any(not isinstance(monster_id, str) for monster_id in monster_ids)
        or len(set(monster_ids)) != 3
    ):
        return error_response("invalid_team", "A team must contain exactly three distinct cards", 400)
    if any(monster_id not in MONSTERS for monster_id in monster_ids):
        return error_response("unknown_card", "Every team card must be in the catalog", 400)
    with connect("collection.sqlite") as db:
        owned = set(owned_ids(db, player_id))
        if not set(monster_ids).issubset(owned):
            return error_response("not_owned", "Your team can only use cards in your collection", 400)
        db.execute(
            """INSERT INTO teams(player_id, slot_1, slot_2, slot_3) VALUES (?, ?, ?, ?)
               ON CONFLICT(player_id) DO UPDATE SET
               slot_1 = excluded.slot_1, slot_2 = excluded.slot_2, slot_3 = excluded.slot_3""",
            (player_id, *monster_ids),
        )
    return jsonify({"playerId": player_id, "team": monster_ids}), 200


@app.get("/internal/players/<player_id>/team")
@internal_required
def get_validated_team(player_id):
    with connect("collection.sqlite") as db:
        ids = owned_ids(db, player_id)
        team_ids = saved_team(db, player_id)
    if team_ids is None or len(team_ids) != 3 or len(set(team_ids)) != 3:
        return error_response("team_unavailable", "A valid three-card team is required", 409)
    if not set(team_ids).issubset(set(ids)):
        return error_response("team_invalid", "The saved team contains a card not owned by the player", 409)
    return jsonify(
        {
            "playerId": player_id,
            "team": [monster_payload(monster_id) for monster_id in team_ids],
            "ownedIds": ids,
        }
    ), 200


@app.post("/internal/players/<player_id>/collection/monsters")
@internal_required
def add_monster(player_id):
    body = request.get_json(silent=True)
    monster_id = body.get("monsterId") if isinstance(body, dict) else None
    if not isinstance(monster_id, str) or monster_id not in MONSTERS:
        return error_response("unknown_card", "A valid catalog card is required", 400)
    with connect("collection.sqlite") as db:
        db.execute(
            "INSERT OR IGNORE INTO collection(player_id, monster_id) VALUES (?, ?)",
            (player_id, monster_id),
        )
        ids = owned_ids(db, player_id)
    return jsonify({"playerId": player_id, "monster": monster_payload(monster_id), "owned": len(ids)}), 200


@app.delete("/internal/players/<player_id>/collection")
@internal_required
def delete_collection(player_id):
    with connect("collection.sqlite") as db:
        db.execute("DELETE FROM teams WHERE player_id = ?", (player_id,))
        db.execute("DELETE FROM collection WHERE player_id = ?", (player_id,))
    return "", 204


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "collector"}), 200


initialize_database()
