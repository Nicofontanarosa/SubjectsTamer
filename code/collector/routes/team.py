from flask import Blueprint, current_app, jsonify, request

from common.game import error_response
from common.storage import connect
from routes.helpers import monster_payload, owned_ids, saved_team

team_bp = Blueprint("team", __name__)

# Updates the player's team with the specified cards.
# The request must contain a JSON array with three distinct card IDs.
# Verifies that every card exists in the catalog and in the player's collection.
@team_bp.put("/players/<player_id>/team")
def update_team(player_id):
    body = request.get_json(silent=True)
    monster_ids = body.get("monsterIds") if isinstance(body, dict) else None
    if (
        not isinstance(monster_ids, list)
        or len(monster_ids) != 3
        or any(not isinstance(monster_id, str) for monster_id in monster_ids)
        or len(set(monster_ids)) != 3
    ):
        return error_response("invalid_team", "A team must contain exactly three distinct cards", 400)
    if any(monster_id not in current_app.config["MONSTERS"] for monster_id in monster_ids):
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

# Returns the player's saved team if it is valid.
# A valid team must contain exactly three distinct cards, all owned by the player.
@team_bp.get("/internal/players/<player_id>/team")
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
