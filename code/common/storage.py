import os
import sqlite3
from pathlib import Path

# Usiamo SQLite poiché è un motore di database relazionale leggero, veloce e basato su file.
def connect(database_name):
    # Cerca una variabile d'ambiente chiamata DATA_DIR. Se esiste, usa quella cartella; altrimenti, cade sul default /data
    database_path = Path(os.environ.get("DATA_DIR", "/data")) / database_name
    database_path.parent.mkdir(parents=True, exist_ok=True)
    # Apre la connessione al file SQLite
    connection = sqlite3.connect(database_path, timeout=10)
    # In Flask potrai scrivere user['email'] o user['id'] invece di ricordarti l'indice numerico
    # della colonna (user[2]), rendendo il codice molto più leggibile e facile da mantenere.
    connection.row_factory = sqlite3.Row
    # Per impostazione predefinita, SQLite disattiva i vincoli di integrità referenziale (le chiavi esterne tra tabelle).
    connection.execute("PRAGMA foreign_keys = ON")
    # Attiva la modalità WAL per la gestione della concorrenza. Invece di bloccare l'intero file del database durante una scrittura, SQLite scrive le modifiche in un file di log separato.
    connection.execute("PRAGMA journal_mode = WAL")
    return connection
