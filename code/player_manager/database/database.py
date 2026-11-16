
import os
import sqlite3
from pathlib import Path


class Database:
    # Eccezioni SQLite utilizzabili dalle altre componenti.
    Error = sqlite3.Error
    IntegrityError = sqlite3.IntegrityError

    def __enter__(self):
        # Recupera la directory del database da Docker Compose.
        path = Path(os.getenv("DATA_DIR", "/data")) / "players.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)

        # Apre il database, attendendo fino a 10 secondi in caso di lock.
        self.connection = sqlite3.connect(path, timeout=10)

        # Permette di leggere le colonne per nome: row["email"].
        self.connection.row_factory = sqlite3.Row

        # Abilita il controllo delle chiavi esterne.
        self.connection.execute("PRAGMA foreign_keys = ON")

        # Restituisce l'istanza utilizzata nel blocco with.
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # Chiamato automaticamente alla fine del blocco with.
        try:
            if exc_type is None:
                self.connection.commit()  # Salva le modifiche.
            else:
                self.connection.rollback()  # Annulla le modifiche.
        finally:
            self.connection.close()  # Chiude sempre la connessione.

    def execute(self, query, parameters=()):
        # Esegue INSERT, UPDATE o DELETE.
        cursor = self.connection.execute(query, parameters)
        try:
            return cursor.rowcount  # Numero di righe interessate.
        finally:
            cursor.close()

    def execute_many(self, query, parameters):
        # Esegue la stessa query con gruppi di parametri diversi.
        cursor = self.connection.executemany(query, parameters)
        try:
            return cursor.rowcount
        finally:
            cursor.close()

    def fetch_one(self, query, parameters=()):
        # Recupera una sola riga, oppure None.
        cursor = self.connection.execute(query, parameters)
        try:
            return cursor.fetchone()
        finally:
            cursor.close()

    def fetch_all(self, query, parameters=()):
        # Recupera tutte le righe, restituendo una lista.
        cursor = self.connection.execute(query, parameters)
        try:
            return cursor.fetchall()
        finally:
            cursor.close()

    @staticmethod
    def initialize_database():
        # Inizializza il database all'avvio del microservizio.
        with Database() as db:
            # Abilita il Write-Ahead Logging.
            db.execute("PRAGMA journal_mode = WAL")

            # Crea la tabella players soltanto se non esiste.
            db.execute("""
                CREATE TABLE IF NOT EXISTS players (
                    player_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    nickname TEXT NOT NULL UNIQUE,
                    avatar TEXT NOT NULL,
                    bio TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)


# =====================================================
# ESEMPI DI UTILIZZO
# =====================================================
# Le variabili degli esempi sono già state preparate
# dalle funzioni di authentication.py e player_profile.py.


# 1. REGISTRAZIONE (authentication.py)
# Inserisce il nuovo player nel database.

# with Database() as db:
#     db.execute(
#         """INSERT INTO players
#            (player_id, email, password_hash, nickname, avatar, bio, created_at)
#            VALUES (?, ?, ?, ?, ?, ?, ?)""",
#         (player_id, email, password_hash, nickname, avatar, bio, created_at)
#     )
# Terminato il with, __exit__ effettua il commit.


# 2. LOGIN (authentication.py)
# Cerca il player associato all'email.

# with Database() as db:
#     player = db.fetch_one(
#         "SELECT * FROM players WHERE email = ?",
#         (email,)
#     )
# player["password_hash"] contiene l'hash da verificare.
# Se non trova il player, restituisce None.


# 3. MODIFICA PROFILO (player_profile.py)
# Aggiorna il nickname e recupera il profilo aggiornato.

# with Database() as db:
#     db.execute(
#         "UPDATE players SET nickname = ? WHERE player_id = ?",
#         (nickname, player_id)
#     )
#     player = db.fetch_one(
#         "SELECT * FROM players WHERE player_id = ?",
#         (player_id,)
#     )
# Entrambe le query utilizzano la stessa connessione.


# 4. ELIMINAZIONE PLAYER (player_profile.py)
# Elimina il player identificato dal suo ID.

# with Database() as db:
#     righe_eliminate = db.execute(
#         "DELETE FROM players WHERE player_id = ?",
#         (player_id,)
#     )
# Restituisce 1 se elimina un record, 0 se non lo trova.


# 5. LETTURA MULTIPLA
# Recupera tutti i player.

# with Database() as db:
#     players = db.fetch_all("SELECT * FROM players")
#
# players[0]["email"]  -> email del primo player
# players[1]["email"]  -> email del secondo player


# 6. AGGIORNAMENTO MULTIPLO
# Modifica l'avatar di due player con una sola chiamata.

# with Database() as db:
#     db.execute_many(
#         "UPDATE players SET avatar = ? WHERE player_id = ?",
#         [("ranger", "123"), ("mage", "456")]
#     )
