"""Accesso al database SQLite del Player Manager."""

import os
import sqlite3
from pathlib import Path


class Database:
    # riportiamo le eccezioni originali di sqlite, usate dalle componenti.
    Error = sqlite3.Error
    IntegrityError = sqlite3.IntegrityError

    # __enter__ e __exit__ permettono di utilizzare: with Database() as db.
    # apriamo una connessione per ogni blocco with, senza condividerla tra richieste.
    def __enter__(self):
        # DATA_DIR arriva da docker compose; il database si trova in /data/players.sqlite.
        path = Path(os.getenv("DATA_DIR", "/data")) / "players.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)

        # apre il file sqlite, creandolo se ancora non esiste.
        # timeout=10 indica quanto aspettare per ottenere un lock sul database.
        self.connection = sqlite3.connect(path, timeout=10)
        self.connection.row_factory = sqlite3.Row  # permette row["email"] invece di row[1].
        self.connection.execute("PRAGMA foreign_keys = ON")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        # all'uscita dal with confermiamo le modifiche oppure le annulliamo.
        try:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()  # annulla le modifiche non ancora confermate.
        finally:
            self.connection.close()  # chiudiamo comunque la connessione.

    def execute(self, query, parameters=()):
        # INSERT, UPDATE e DELETE: restituisce il numero di righe interessate.
        # i ? della query vengono riempiti con i parametri, senza concatenare stringhe sql.
        cursor = self.connection.execute(query, parameters)
        try:
            return cursor.rowcount
        finally:
            cursor.close()

    def execute_many(self, query, parameters):
        # esegue la stessa istruzione sql su più gruppi di parametri.
        cursor = self.connection.executemany(query, parameters)
        try:
            return cursor.rowcount
        finally:
            cursor.close()

    def fetch_one(self, query, parameters=()):
        # restituisce una sola riga sqlite3.Row oppure None.
        cursor = self.connection.execute(query, parameters)
        try:
            return cursor.fetchone()
        finally:
            cursor.close()

    def fetch_all(self, query, parameters=()):
        # restituisce una lista di righe, eventualmente vuota.
        cursor = self.connection.execute(query, parameters)
        try:
            return cursor.fetchall()
        finally:
            cursor.close()

    @staticmethod
    def initialize_database():
        # viene chiamata all'avvio del servizio: crea la tabella se non esiste.
        with Database() as db:
            # WAL permette ai lettori di continuare mentre un'altra connessione scrive.
            # sqlite consente comunque un solo writer alla volta.
            db.execute("PRAGMA journal_mode = WAL")
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