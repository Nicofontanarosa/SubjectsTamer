"""Prepara un database SQLite isolato per i component test di Player Manager.

Eseguito dal container seed prima di avviare il servizio, sullo stesso volume.
Non utilizzare su database di produzione: elimina tutte le righe di players.
"""

from datetime import datetime, timezone

from werkzeug.security import generate_password_hash
from database import Database

TEST_PASSWORD = "TestPassword123!"
CREATED_AT = "2026-11-17T12:00:00+00:00"

# ID stabili: stessi valori usati dall'ambiente Bruno.
PLAYERS = (
    ("test-player-123", "player.test@example.com", "TestPlayer", "ranger", "Initial profile"),
    ("test-player-secondary", "player.second@example.com", "ExistingPlayer", "mage", "Secondary account"),
    ("test-player-delete", "player.delete@example.com", "DeletePlayer", "warrior", "To be deleted"),
    ("test-player-failed-delete", "player.faildelete@example.com", "FailDeletePlayer", "ranger", "Must survive a failed cleanup"),
)

Database.initialize_database()
with Database() as db:
    db.execute("DELETE FROM players")
    db.execute_many(
        """INSERT INTO players
           (player_id, email, password_hash, nickname, avatar, bio, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [
            (player_id, email, generate_password_hash(TEST_PASSWORD), nickname, avatar, bio, CREATED_AT)
            for player_id, email, nickname, avatar, bio in PLAYERS
        ],
    )

print(f"Seeded {len(PLAYERS)} players in isolated test database")
