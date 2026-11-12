import base64
import hashlib
import json
import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from common.game import error_response
from common.storage import connect

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
COLLECTOR_URL = os.environ.get("COLLECTOR_URL", "http://collector:5005").rstrip("/")
ENCOUNTER_URL = os.environ.get("ENCOUNTER_URL", "http://encounter:5005").rstrip("/")
GAME_MANAGER_URL = os.environ.get("GAME_MANAGER_URL", "http://game-manager:5005").rstrip("/")
TUTORIAL_PATH = Path(os.environ.get("TUTORIAL_PATH", "/app/tutorial.json"))
LEGACY_ENCRYPTION_SECRET = os.environ.get(
    "DATA_ENCRYPTION_KEY", "local-development-data-encryption-secret-change-before-deployment"
)
LEGACY_ENCRYPTION_KEY = base64.urlsafe_b64encode(
    hashlib.sha256(LEGACY_ENCRYPTION_SECRET.encode()).digest()
)


def migrate_legacy_player_data(db):
    tables = {
        row["name"]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    if "players" not in tables:
        return
    columns = {row["name"] for row in db.execute("PRAGMA table_info(players)").fetchall()}
    if "email_ciphertext" not in columns:
        return

    legacy_rows = db.execute("SELECT * FROM players").fetchall()
    cipher = Fernet(LEGACY_ENCRYPTION_KEY)
    try:
        migrated_rows = [
            (
                row["player_id"],
                cipher.decrypt(row["email_ciphertext"]).decode("utf-8"),
                row["password_hash"],
                row["nickname"],
                row["avatar"],
                cipher.decrypt(row["bio_ciphertext"]).decode("utf-8"),
                row["created_at"],
            )
            for row in legacy_rows
        ]
    except (InvalidToken, ValueError, TypeError) as exc:
        raise RuntimeError(
            "Existing player data could not be migrated. Set DATA_ENCRYPTION_KEY to the key "
            "used by the previous version, start once to migrate, then remove it."
        ) from exc

    db.execute("DROP TABLE IF EXISTS sessions")
    db.execute("ALTER TABLE players RENAME TO players_encrypted_legacy")
    db.execute(
        """CREATE TABLE players (
            player_id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            nickname TEXT NOT NULL UNIQUE,
            avatar TEXT NOT NULL,
            bio TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
    )
    db.executemany(
        """INSERT INTO players
           (player_id, email, password_hash, nickname, avatar, bio, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        migrated_rows,
    )
    db.execute("DROP TABLE players_encrypted_legacy")
    app.logger.info("Migrated legacy encrypted player profiles to the plain-text profile schema")


def initialize_database():
    with connect("players.sqlite") as db:
        migrate_legacy_player_data(db)
        db.execute(
            """CREATE TABLE IF NOT EXISTS players (
                player_id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                nickname TEXT NOT NULL UNIQUE,
                avatar TEXT NOT NULL,
                bio TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )


def internal_request(method, url, *, json_body=None):
    return requests.request(method, url, json=json_body, timeout=5)


def player_profile(row):
    return {
        "playerId": row["player_id"],
        "email": row["email"],
        "nickname": row["nickname"],
        "avatar": row["avatar"],
        "bio": row["bio"],
        "createdAt": row["created_at"],
    }


@app.post("/players")
def register_player():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response("invalid_request", "A JSON object is required", 400)
    email = body.get("email")
    password = body.get("password")
    nickname = body.get("nickname")
    avatar = body.get("avatar", "ranger")
    bio = body.get("bio", "")
    if not isinstance(email, str) or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email.strip()):
        return error_response("invalid_email", "Enter a valid email address", 400)
    if not isinstance(password, str) or len(password) < 10:
        return error_response("weak_password", "Password must contain at least 10 characters", 400)
    if not isinstance(nickname, str) or not nickname.strip() or len(nickname.strip()) > 32:
        return error_response("invalid_nickname", "Nickname must contain 1 to 32 characters", 400)
    if not isinstance(avatar, str) or len(avatar) > 40 or not isinstance(bio, str) or len(bio) > 500:
        return error_response("invalid_profile", "Avatar or biography is too long", 400)

    player_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        with connect("players.sqlite") as db:
            db.execute(
                """INSERT INTO players
                   (player_id, email, password_hash, nickname, avatar, bio, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    player_id,
                    email.strip().lower(),
                    generate_password_hash(password),
                    nickname.strip(),
                    avatar,
                    bio.strip(),
                    created_at,
                ),
            )
    except sqlite3.IntegrityError as exc:
        if "UNIQUE constraint failed" in str(exc):
            return error_response("account_exists", "Email or nickname is already in use", 409)
        app.logger.exception("Could not create player account")
        return error_response("storage_error", "The account could not be created", 500)
    except sqlite3.Error:
        app.logger.exception("Could not create player account")
        return error_response("storage_error", "The account could not be created", 500)

    try:
        response = internal_request(
            "POST",
            f"{COLLECTOR_URL}/internal/players/{player_id}/collection/initialize",
        )
        if response.status_code not in (200, 201):
            app.logger.error("Collector initialization failed: %s", response.status_code)
            with connect("players.sqlite") as db:
                db.execute("DELETE FROM players WHERE player_id = ?", (player_id,))
            return error_response("initialization_failed", "The starting collection could not be created", 502)
    except requests.RequestException:
        app.logger.exception("Collector could not be reached during registration")
        with connect("players.sqlite") as db:
            db.execute("DELETE FROM players WHERE player_id = ?", (player_id,))
        return error_response("service_unavailable", "The collection service is unavailable", 502)

    with connect("players.sqlite") as db:
        row = db.execute("SELECT * FROM players WHERE player_id = ?", (player_id,)).fetchone()
    return jsonify({"player": player_profile(row)}), 201


@app.post("/auth/login")
def login():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response("invalid_request", "A JSON object is required", 400)
    email, password = body.get("email"), body.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        return error_response("invalid_credentials", "Email or password is incorrect", 401)
    with connect("players.sqlite") as db:
        row = db.execute(
            "SELECT * FROM players WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        return error_response("invalid_credentials", "Email or password is incorrect", 401)
    return jsonify({"player": player_profile(row)}), 200


@app.post("/auth/logout")
def logout():
    return "", 204


@app.get("/players/<player_id>")
def get_player(player_id):
    with connect("players.sqlite") as db:
        row = db.execute("SELECT * FROM players WHERE player_id = ?", (player_id,)).fetchone()
    if row is None:
        return error_response("not_found", "Player not found", 404)
    return jsonify({"player": player_profile(row)}), 200


@app.put("/players/<player_id>")
def update_player(player_id):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response("invalid_request", "A JSON object is required", 400)
    nickname = body.get("nickname")
    avatar = body.get("avatar")
    bio = body.get("bio")
    if (
        not isinstance(nickname, str)
        or not nickname.strip()
        or len(nickname.strip()) > 32
        or not isinstance(avatar, str)
        or len(avatar) > 40
        or not isinstance(bio, str)
        or len(bio) > 500
    ):
        return error_response("invalid_profile", "Profile details are invalid", 400)
    try:
        with connect("players.sqlite") as db:
            db.execute(
                "UPDATE players SET nickname = ?, avatar = ?, bio = ? WHERE player_id = ?",
                (nickname.strip(), avatar, bio.strip(), player_id),
            )
            row = db.execute("SELECT * FROM players WHERE player_id = ?", (player_id,)).fetchone()
    except sqlite3.IntegrityError as exc:
        if "UNIQUE constraint failed" in str(exc):
            return error_response("nickname_taken", "That nickname is already in use", 409)
        app.logger.exception("Could not update player profile")
        return error_response("storage_error", "The profile could not be saved", 500)
    except sqlite3.Error:
        app.logger.exception("Could not update player profile")
        return error_response("storage_error", "The profile could not be saved", 500)
    if row is None:
        return error_response("not_found", "Player not found", 404)
    return jsonify({"player": player_profile(row)}), 200


@app.delete("/players/<player_id>")
def delete_player(player_id):
    with connect("players.sqlite") as db:
        existing = db.execute("SELECT 1 FROM players WHERE player_id = ?", (player_id,)).fetchone()
    if existing is None:
        return error_response("not_found", "Player not found", 404)
    failures = []
    for service_url, path in (
        (COLLECTOR_URL, f"/internal/players/{player_id}/collection"),
        (ENCOUNTER_URL, f"/internal/players/{player_id}/encounters"),
        (GAME_MANAGER_URL, f"/internal/players/{player_id}/battles"),
    ):
        try:
            response = internal_request("DELETE", f"{service_url}{path}")
            if response.status_code not in (200, 204, 404):
                failures.append(service_url)
        except requests.RequestException:
            app.logger.exception("Account cleanup request failed for %s", service_url)
            failures.append(service_url)
    if failures:
        return error_response(
            "cleanup_incomplete",
            "Some game data could not be removed. Retry account deletion to finish cleanup.",
            502,
        )
    with connect("players.sqlite") as db:
        db.execute("DELETE FROM players WHERE player_id = ?", (player_id,))
    return "", 204


@app.get("/tutorial")
def tutorial():
    try:
        with TUTORIAL_PATH.open(encoding="utf-8") as tutorial_file:
            return jsonify(json.load(tutorial_file)), 200
    except (OSError, json.JSONDecodeError):
        app.logger.exception("Tutorial file could not be read")
        return error_response("tutorial_unavailable", "The field guide is unavailable", 500)


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "player-manager"}), 200


initialize_database()
