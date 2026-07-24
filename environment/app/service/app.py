"""Fixed Flask deployment target for Vault Maze automation.

This service is deployment infrastructure only. It mirrors the routes
described in /app/data/flask_api_contract.json so the environment reads like
a real target system, but it holds no release-planning logic. The
release-lock compiler never calls this service over HTTP; it only reads the
static contract document.
"""

from __future__ import annotations

from flask import Flask, jsonify, request

app = Flask(__name__)


def _accept(extra: dict | None = None) -> tuple:
    body = {"status": "ok"}
    if extra:
        body.update(extra)
    return jsonify(body), 200


@app.post("/api/vault/auth")
def vault_auth():
    request.get_json(silent=True)
    return _accept({"session": "vault-session-fixed"})


@app.post("/api/maze/enter")
def maze_enter():
    request.get_json(silent=True)
    return _accept({"maze": "maze-entry-fixed"})


@app.post("/api/clue/legacy-sync")
def clue_legacy_sync():
    request.get_json(silent=True)
    return _accept({"sync": "legacy-clue-sync-fixed"})


@app.route("/api/route/unlock", methods=["POST", "PATCH"])
def route_unlock():
    request.get_json(silent=True)
    return _accept({"route": "route-unlock-fixed"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080)
