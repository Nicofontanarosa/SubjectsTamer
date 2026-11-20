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
