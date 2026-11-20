from app import app
from common.storage import connect

PLAYER_ID = "test-player-123"
COLLECTION_IDS = (
    "programming-algorithms",
    "mathematical-analysis",
    "misure-elettroniche",
    "chimiche-della-vita",
    "biologia-molecolare",
)
TEAM_IDS = (
    "programming-algorithms",
    "mathematical-analysis",
    "misure-elettroniche",
)

if len(COLLECTION_IDS) != 5 or len(set(COLLECTION_IDS)) != 5:
    raise ValueError("The test collection must contain five distinct monsters")
if len(TEAM_IDS) != 3 or len(set(TEAM_IDS)) != 3:
    raise ValueError("The test team must contain three distinct monsters")
if not set(TEAM_IDS).issubset(COLLECTION_IDS):
    raise ValueError("Every team monster must belong to the test collection")

monsters = app.config["MONSTERS"]
unknown_ids = set(COLLECTION_IDS) - monsters.keys()
if unknown_ids:
    raise ValueError(f"Unknown test monster IDs: {sorted(unknown_ids)}")

db = connect("collection.sqlite")
try:
    with db:
        db.execute("DELETE FROM teams")
        db.execute("DELETE FROM collection")
        db.executemany(
            "INSERT INTO collection(player_id, monster_id) VALUES (?, ?)",
            [(PLAYER_ID, monster_id) for monster_id in COLLECTION_IDS],
        )
        db.execute(
            "INSERT INTO teams(player_id, slot_1, slot_2, slot_3) VALUES (?, ?, ?, ?)",
            (PLAYER_ID, *TEAM_IDS),
        )
finally:
    db.close()
