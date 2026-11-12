import json
import os
import secrets
from functools import wraps
from pathlib import Path

import jwt
from flask import jsonify, request

CATALOG_PATH = Path(os.environ.get("CATALOG_PATH", "/app/shared/catalog.json"))
JWT_SECRET = os.environ.get("JWT_SECRET", "replace-this-development-secret")
INTERNAL_TOKEN = os.environ.get("INTERNAL_TOKEN", "replace-this-internal-token")
JWT_ALGORITHM = "HS256"
TLS_CA = os.environ.get("TLS_CA", "/certs/ca.pem")


def tls_verify():
    if os.path.isfile(TLS_CA):
        return TLS_CA
    return False


def load_catalog():
    with CATALOG_PATH.open(encoding="utf-8") as catalog_file:
        catalog = json.load(catalog_file)
    return catalog, {monster["id"]: monster for monster in catalog}


def add_stats(monster):
    cfu = monster["cfu"]
    stats = monster.get("baseStats") or {
        "hp": 95 + 7 * cfu,
        "attack": round(12 + 1.5 * cfu),
        "defense": round(8 + 1.2 * cfu),
    }
    return {
        **monster,
        "rarity": rarity(cfu),
        "stats": stats,
        "imageUrl": f"/monsters/{monster['id']}/image",
    }


def rarity(cfu):
    if cfu >= 15:
        return "Legendary"
    if cfu >= 12:
        return "Epic"
    if cfu >= 9:
        return "Rare"
    if cfu >= 6:
        return "Uncommon"
    return "Common"


def error_response(code, message, status):
    return jsonify({"error": code, "message": message}), status


def internal_authorized():
    supplied = request.headers.get("X-Internal-Token", "")
    return secrets.compare_digest(supplied, INTERNAL_TOKEN)


def internal_required(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        if not internal_authorized():
            return error_response("forbidden", "Internal access only", 403)
        return function(*args, **kwargs)

    return wrapped


def bearer_token():
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def token_claims(token=None):
    token = token or bearer_token()
    if not token:
        return None
    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if not isinstance(claims.get("sub"), str) or not isinstance(claims.get("jti"), str):
        return None
    return claims


def authenticated_player_id():
    claims = token_claims()
    return claims.get("sub") if claims else None


def require_player_access(player_id):
    authenticated_id = authenticated_player_id()
    if authenticated_id is None:
        return error_response("unauthorized", "Sign in to continue", 401)
    if authenticated_id != player_id:
        return error_response("forbidden", "You can only access your own profile", 403)
    return None


def internal_headers():
    return {"X-Internal-Token": INTERNAL_TOKEN}
