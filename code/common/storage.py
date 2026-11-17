import os
import sqlite3
from pathlib import Path

# We use SQLite because it is a lightweight, fast, file-based relational database.
def connect(database_name):
    # Use the DATA_DIR environment variable if set; otherwise, default to /data.
    database_path = Path(os.environ.get("DATA_DIR", "/data")) / database_name
    database_path.parent.mkdir(parents=True, exist_ok=True)
    # Open a connection to the SQLite database file.
    connection = sqlite3.connect(database_path, timeout=10)
    # In Flask, access columns by name (e.g. user['email'] or user['id']) rather than by index (e.g. user[2]),
    # making the code easier to read and maintain.
    connection.row_factory = sqlite3.Row
    # Enable foreign key constraints, which SQLite disables by default.
    connection.execute("PRAGMA foreign_keys = ON")
    # Enable WAL mode for concurrency: SQLite writes changes to a separate log file instead of locking the entire database file.
    connection.execute("PRAGMA journal_mode = WAL")
    return connection
