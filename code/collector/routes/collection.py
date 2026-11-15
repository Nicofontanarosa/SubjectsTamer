import random

from flask import Blueprint, current_app, jsonify, request

from common.game import error_response
from common.storage import connect
from routes.helpers import monster_payload, owned_ids, saved_team

collection_bp = Blueprint("collection", __name__)


@collection_bp.post("/internal/players/<player_id>/collection/initialize")
def initialize_collection(player_id):
    catalog = current_app.config["CATALOG"]
    candidates = [monster for monster in catalog if monster["cfu"] in (6, 9)]
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


@collection_bp.get("/players/<player_id>/collection")
def get_collection(player_id):
    with connect("collection.sqlite") as db:
        ids = owned_ids(db, player_id)
        team_ids = saved_team(db, player_id)
    return jsonify(
        {
            "monsters": [monster_payload(monster_id) for monster_id in ids],
            "team": team_ids or [],
            "progress": {"owned": len(ids), "total": len(current_app.config["CATALOG"])},
        }
    ), 200


@collection_bp.post("/internal/players/<player_id>/collection/monsters")
def add_monster(player_id):
    monster_id = request.get_json(silent=True)
    monster_id = monster_id.get("monsterId") if isinstance(monster_id, dict) else None
    monsters = current_app.config["MONSTERS"]
    if not isinstance(monster_id, str) or monster_id not in monsters:
        return error_response("unknown_card", "A valid catalog card is required", 400)
    with connect("collection.sqlite") as db:
        db.execute(
            "INSERT OR IGNORE INTO collection(player_id, monster_id) VALUES (?, ?)",
            (player_id, monster_id),
        )
        ids = owned_ids(db, player_id)
    return jsonify({"playerId": player_id, "monster": monster_payload(monster_id), "owned": len(ids)}), 200


@collection_bp.delete("/internal/players/<player_id>/collection")
def delete_collection(player_id):
    with connect("collection.sqlite") as db:
        db.execute("DELETE FROM teams WHERE player_id = ?", (player_id,))
        db.execute("DELETE FROM collection WHERE player_id = ?", (player_id,))
    return "", 204
