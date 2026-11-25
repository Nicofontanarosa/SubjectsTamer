from flask import current_app

from common.game import error_response

# Logs the database exception and returns the attempted operation without exposing database details.
def database_error_response(operation):
    current_app.logger.exception("Database operation failed while %s", operation)
    return error_response("database_error", operation, 500)

# Returns a list of monster IDs owned by the specified player, ordered by acquisition time and then by monster ID.
def owned_ids(db, player_id):
    rows = db.execute(
        "SELECT monster_id FROM collection WHERE player_id = ? ORDER BY acquired_at, monster_id",
        (player_id,),
    ).fetchall()
    return [row["monster_id"] for row in rows]

# Returns the player's saved team as a list of monster IDs, or None if the player has no saved team.
def saved_team(db, player_id):
    row = db.execute(
        "SELECT slot_1, slot_2, slot_3 FROM teams WHERE player_id = ?", (player_id,)
    ).fetchone()
    return list(row) if row else None
