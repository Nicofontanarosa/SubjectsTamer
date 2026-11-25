import time
from collections import Counter
from threading import Lock

from flask import Flask, jsonify, request

app = Flask(__name__)
lock = Lock()
encounter_calls = Counter()


@app.post("/internal/encounters")
def record_encounter():
    body = request.get_json(silent=True)
    player_id = body.get("playerId") if isinstance(body, dict) else None

    if player_id == "history-timeout":
        time.sleep(6)
    if player_id in ("history-retry", "history-abandon-retry"):
        with lock:
            encounter_calls[player_id] += 1
            first_attempt = encounter_calls[player_id] == 1
        if first_attempt:
            return jsonify({"error": "simulated_history_failure"}), 503

    if not isinstance(body, dict) or not body.get("battleId"):
        return jsonify({"error": "invalid_encounter_request"}), 400
    return jsonify({"status": "recorded", "battleId": body["battleId"]}), 201


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "encounter-stub"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5005, threaded=True)
