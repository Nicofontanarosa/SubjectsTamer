import logging
import os
import re
import uuid

import requests
from flask import Flask, Response, jsonify, make_response, request

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
PLAYER_MANAGER_URL = os.environ.get("PLAYER_MANAGER_URL", "http://player-manager:5005").rstrip("/")
COLLECTOR_URL = os.environ.get("COLLECTOR_URL", "http://collector:5005").rstrip("/")
GAME_MANAGER_URL = os.environ.get("GAME_MANAGER_URL", "http://game-manager:5005").rstrip("/")
ENCOUNTER_URL = os.environ.get("ENCOUNTER_URL", "http://encounter:5005").rstrip("/")
REQUEST_TIMEOUT = 8
CORS_ORIGINS = {
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000"
    ).split(",")
    if origin.strip()
}


def json_error(code, message, status):
    return jsonify({"error": code, "message": message}), status


def target_for(path, method):
    if path == "players" and method == "POST":
        return PLAYER_MANAGER_URL
    if path in ("auth/login", "auth/logout") and method == "POST":
        return PLAYER_MANAGER_URL
    if path == "tutorial" and method == "GET":
        return PLAYER_MANAGER_URL
    if path == "monsters" and method == "GET":
        return COLLECTOR_URL
    if re.fullmatch(r"monsters/[^/]+/image", path) and method == "GET":
        return COLLECTOR_URL
    if path == "battles" and method == "POST":
        return GAME_MANAGER_URL
    if re.fullmatch(r"battles/[^/]+/actions", path) and method == "POST":
        return GAME_MANAGER_URL
    if re.fullmatch(r"battles/[^/]+", path) and method == "POST":
        return GAME_MANAGER_URL

    player_match = re.fullmatch(r"players/([^/]+)", path)
    if player_match and method in ("GET", "PUT", "DELETE"):
        return PLAYER_MANAGER_URL
    if re.fullmatch(r"players/[^/]+/collection", path) and method == "GET":
        return COLLECTOR_URL
    if re.fullmatch(r"players/[^/]+/team", path) and method == "PUT":
        return COLLECTOR_URL
    if re.fullmatch(r"players/[^/]+/encounters", path) and method == "GET":
        return ENCOUNTER_URL
    if path.startswith("internal/"):
        return None
    return None


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin in CORS_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        response.headers["Access-Control-Max-Age"] = "600"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.route("/<path:public_path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
def dispatch(public_path):
    if request.method == "OPTIONS":
        return make_response("", 204)
    target_url = target_for(public_path, request.method)
    if target_url is None:
        return json_error("not_found", "API route not found", 404)

    headers = {
        key: value
        for key, value in request.headers
        if key.lower() in ("content-type", "accept")
    }
    upstream_url = f"{target_url}/{public_path}"
    try:
        upstream = requests.request(
            request.method,
            upstream_url,
            params=request.args,
            data=request.get_data() if request.method not in ("GET", "HEAD") else None,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=False,
        )
    except requests.Timeout:
        return json_error("upstream_timeout", "The requested service timed out", 504)
    except requests.RequestException:
        app.logger.exception("Could not reach API service for %s", public_path)
        return json_error("upstream_unavailable", "The requested service is unavailable", 502)

    content_type = upstream.headers.get("Content-Type", "application/json")
    return Response(
        upstream.content,
        status=upstream.status_code,
        content_type=content_type,
        headers={"X-Request-ID": str(uuid.uuid4())},
    )


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "api-gateway"}), 200


@app.get("/")
def root():
    return jsonify({"service": "monster-tamer-api", "health": "/health"}), 200
