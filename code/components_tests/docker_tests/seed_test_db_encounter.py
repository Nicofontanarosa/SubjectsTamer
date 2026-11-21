import json

from app import MONSTERS, initialize_database
from common.storage import connect

PLAYER_ID = "test-player-123"
BOSS_ID = "computer-science-foundations"
TEAM_IDS = (
    "linear-algebra",
    "computer-science-lab-ii",
    "operations-research",
)
ENCODED_TEAM = json.dumps(list(TEAM_IDS), separators=(",", ":"))

SEED_ENCOUNTERS = (
    {
        "battle_id": "seed-battle-01",
        "player_id": PLAYER_ID,
        "boss_id": BOSS_ID,
        "team_json": ENCODED_TEAM,
        "result": "win",
        "outcome": "Victory by knockout",
        "turns": 5,
        "started_at": "2026-11-17T11:55:00Z",
        "completed_at": "2026-11-17T12:00:00Z",
    },
    {
        "battle_id": "seed-battle-02",
        "player_id": PLAYER_ID,
        "boss_id": BOSS_ID,
        "team_json": ENCODED_TEAM,
        "result": "loss",
        "outcome": "loss",
        "turns": 3,
        "started_at": "2026-11-17T13:00:00Z",
        "completed_at": "2026-11-17T13:00:00Z",
    },
)

if len(TEAM_IDS) != 3 or len(set(TEAM_IDS)) != 3:
    raise ValueError("The test team must contain three distinct cards")

required_ids = set(TEAM_IDS) | {BOSS_ID}
unknown_ids = required_ids - MONSTERS.keys()
if unknown_ids:
    raise ValueError(f"Unknown test IDs in catalog: {sorted(unknown_ids)}")

# Garantisce che tabella e indice esistano anche se il seed gira per primo.
initialize_database()

db = connect("encounters.sqlite")
try:
    with db:
        db.execute("DELETE FROM encounters")
        db.executemany(
            """
            INSERT INTO encounters (
                battle_id,
                player_id,
                boss_id,
                team_json,
                result,
                outcome,
                turns,
                started_at,
                completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["battle_id"],
                    row["player_id"],
                    row["boss_id"],
                    row["team_json"],
                    row["result"],
                    row["outcome"],
                    row["turns"],
                    row["started_at"],
                    row["completed_at"],
                )
                for row in SEED_ENCOUNTERS
            ],
        )
finally:
    db.close()