import logging
import os
import re
import uuid

import requests
from flask import Flask, Response, jsonify, make_response, request

from common.game import tls_verify

app = Flask(__name__)
app.logger.setLevel(logging.INFO)
PLAYER_MANAGER_URL = os.environ.get("PLAYER_MANAGER_URL", "https://player-manager:5005").rstrip("/")
COLLECTOR_URL = os.environ.get("COLLECTOR_URL", "https://collector:5005").rstrip("/")
GAME_MANAGER_URL = os.environ.get("GAME_MANAGER_URL", "https://game-manager:5005").rstrip("/")
ENCOUNTER_URL = os.environ.get("ENCOUNTER_URL", "https://encounter:5005").rstrip("/")
INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "replace-this-internal-token")
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
    if path == "auth/session" and method == "GET":
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


def introspect(token):
    try:
        response = requests.get(
            f"{PLAYER_MANAGER_URL}/internal/auth/introspect",
            headers={"Authorization": f"Bearer {token}", "X-Internal-Token": INTERNAL_TOKEN},
            timeout=REQUEST_TIMEOUT,
            verify=tls_verify(),
        )
    except requests.Timeout:
        return None, json_error("auth_service_timeout", "Authentication service timed out", 504)
    except requests.RequestException:
        app.logger.exception("Authentication service is unavailable")
        return None, json_error("auth_service_unavailable", "Authentication service is unavailable", 502)
    if response.status_code != 200:
        return None, json_error("unauthorized", "Sign in to continue", 401)
    try:
        payload = response.json()
    except ValueError:
        app.logger.error("Authentication service returned invalid JSON")
        return None, json_error("auth_service_unavailable", "Authentication service returned an invalid response", 502)
    if not isinstance(payload, dict) or not isinstance(payload.get("playerId"), str):
        return None, json_error("auth_service_unavailable", "Authentication service returned an invalid response", 502)
    return payload, None


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin in CORS_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
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

    token = None
    if not (public_path == "players" and request.method == "POST") and not (
        public_path == "auth/login" and request.method == "POST"
    ):
        authorization = request.headers.get("Authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return json_error("unauthorized", "A bearer access token is required", 401)
        _, failure = introspect(token)
        if failure is not None:
            return failure

    headers = {
        key: value
        for key, value in request.headers
        if key.lower() in ("authorization", "content-type", "accept")
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
            verify=tls_verify(),
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


@app.get("/ca.pem")
def certificate_authority():
    ca_path = os.environ.get("TLS_CA", "/certs/ca.pem")
    try:
        with open(ca_path, "rb") as ca_file:
            return Response(ca_file.read(), status=200, content_type="application/x-pem-file")
    except OSError:
        app.logger.exception("Local certificate authority could not be read")
        return json_error("certificate_unavailable", "The local CA certificate is unavailable", 500)


@app.get("/")
def root():
    return jsonify({"service": "monster-tamer-api", "health": "/health"}), 200
