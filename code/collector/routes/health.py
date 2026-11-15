from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)

# Handles GET requests to the /health endpoint.
@health_bp.get("/health")
def health():
    return jsonify({"status": "ok", "service": "collector"}), 200
