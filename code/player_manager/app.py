import base64
import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import requests
from cryptography.fernet import Fernet
from flask import Flask, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from common.game import (
    INTERNAL_TOKEN,
    JWT_ALGORITHM,
    JWT_SECRET,
    error_response,
    internal_required,
    tls_verify,
    token_claims,
)
from common.storage import connect

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
COLLECTOR_URL = os.environ.get("COLLECTOR_URL", "https://collector:5005").rstrip("/")
ENCOUNTER_URL = os.environ.get("ENCOUNTER_URL", "https://encounter:5005").rstrip("/")
GAME_MANAGER_URL = os.environ.get("GAME_MANAGER_URL", "https://game-manager:5005").rstrip("/")
TUTORIAL_PATH = Path(os.environ.get("TUTORIAL_PATH", "/app/tutorial.json"))
SESSION_HOURS = int(os.environ.get("SESSION_HOURS", "12"))
ENCRYPTION_SECRET = os.environ.get(
    "DATA_ENCRYPTION_KEY", "local-development-data-encryption-secret-change-before-deployment"
)
ENCRYPTION_KEY = base64.urlsafe_b64encode(hashlib.sha256(ENCRYPTION_SECRET.encode()).digest())
CIPHER = Fernet(ENCRYPTION_KEY)


def email_lookup(normalized_email):
    return hmac.new(ENCRYPTION_KEY, normalized_email.encode(), hashlib.sha256).hexdigest()


def decrypt_text(value):
    return CIPHER.decrypt(value).decode("utf-8")


def initialize_database():
    with connect("players.sqlite") as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS players (
                player_id TEXT PRIMARY KEY,
                email_hash TEXT NOT NULL UNIQUE,
                email_ciphertext BLOB NOT NULL,
                password_hash TEXT NOT NULL,
                nickname TEXT NOT NULL UNIQUE,
                avatar TEXT NOT NULL,
                bio_ciphertext BLOB NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_id TEXT PRIMARY KEY,
                player_id TEXT NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
                expires_at TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            );
            """
        )


def issue_token(player_id):
    token_id = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS)
    token = jwt.encode(
        {"sub": player_id, "jti": token_id, "iat": datetime.now(timezone.utc), "exp": expires_at},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )
    with connect("players.sqlite") as db:
        db.execute(
            "INSERT INTO sessions(token_id, player_id, expires_at) VALUES (?, ?, ?)",
            (token_id, player_id, expires_at.isoformat()),
        )
    return token


def internal_request(method, url, *, json_body=None):
    return requests.request(
        method,
        url,
        json=json_body,
        headers={"X-Internal-Token": INTERNAL_TOKEN},
        timeout=5,
        verify=tls_verify(),
    )


def player_profile(row):
    return {
        "playerId": row["player_id"],
        "email": decrypt_text(row["email_ciphertext"]),
        "nickname": row["nickname"],
        "avatar": row["avatar"],
        "bio": decrypt_text(row["bio_ciphertext"]),
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
                   (player_id, email_hash, email_ciphertext, password_hash, nickname, avatar, bio_ciphertext, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    player_id,
                    email_lookup(email.strip().lower()),
                    CIPHER.encrypt(email.strip().lower().encode()),
                    generate_password_hash(password),
                    nickname.strip(),
                    avatar,
                    CIPHER.encrypt(bio.strip().encode()),
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
    return jsonify({"player": player_profile(row), "accessToken": issue_token(player_id)}), 201


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
            "SELECT * FROM players WHERE email_hash = ?",
            (email_lookup(email.strip().lower()),),
        ).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        return error_response("invalid_credentials", "Email or password is incorrect", 401)
    return jsonify({"player": player_profile(row), "accessToken": issue_token(row["player_id"])}), 200


@app.post("/auth/logout")
def logout():
    claims = token_claims()
    if claims is None:
        return error_response("unauthorized", "Sign in to continue", 401)
    with connect("players.sqlite") as db:
        db.execute("UPDATE sessions SET revoked = 1 WHERE token_id = ?", (claims["jti"],))
    return "", 204


@app.get("/auth/session")
def current_session():
    claims = token_claims()
    if claims is None:
        return error_response("unauthorized", "Sign in to continue", 401)
    with connect("players.sqlite") as db:
        row = db.execute(
            """SELECT players.* FROM players
               JOIN sessions ON sessions.player_id = players.player_id
               WHERE sessions.token_id = ? AND sessions.revoked = 0""",
            (claims["jti"],),
        ).fetchone()
    if row is None:
        return error_response("unauthorized", "The session has ended", 401)
    return jsonify({"player": player_profile(row)}), 200


@app.get("/internal/auth/introspect")
@internal_required
def introspect():
    claims = token_claims()
    if claims is None:
        return error_response("unauthorized", "The access token is invalid", 401)
    with connect("players.sqlite") as db:
        session = db.execute(
            """SELECT revoked, expires_at FROM sessions
               WHERE token_id = ? AND player_id = ?""",
            (claims["jti"], claims["sub"]),
        ).fetchone()
    if session is None or session["revoked"]:
        return error_response("unauthorized", "The session has ended", 401)
    if datetime.fromisoformat(session["expires_at"]) <= datetime.now(timezone.utc):
        return error_response("unauthorized", "The session has expired", 401)
    return jsonify({"playerId": claims["sub"], "active": True}), 200


@app.get("/players/<player_id>")
def get_player(player_id):
    claims = token_claims()
    if claims is None:
        return error_response("unauthorized", "Sign in to continue", 401)
    if claims["sub"] != player_id:
        return error_response("forbidden", "You can only view your own profile", 403)
    with connect("players.sqlite") as db:
        row = db.execute("SELECT * FROM players WHERE player_id = ?", (player_id,)).fetchone()
    if row is None:
        return error_response("not_found", "Player not found", 404)
    return jsonify({"player": player_profile(row)}), 200


@app.put("/players/<player_id>")
def update_player(player_id):
    claims = token_claims()
    if claims is None:
        return error_response("unauthorized", "Sign in to continue", 401)
    if claims["sub"] != player_id:
        return error_response("forbidden", "You can only update your own profile", 403)
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
                "UPDATE players SET nickname = ?, avatar = ?, bio_ciphertext = ? WHERE player_id = ?",
                (nickname.strip(), avatar, CIPHER.encrypt(bio.strip().encode()), player_id),
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
    claims = token_claims()
    if claims is None:
        return error_response("unauthorized", "Sign in to continue", 401)
    if claims["sub"] != player_id:
        return error_response("forbidden", "You can only delete your own account", 403)
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
    claims = token_claims()
    if claims is None:
        return error_response("unauthorized", "Sign in to continue", 401)
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
