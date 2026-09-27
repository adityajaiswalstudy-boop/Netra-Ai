"""
AI SafePath — Local Development Server

Lightweight Flask server for local development and testing.
Bridges the mobile PWA to n8n Cloud webhooks.
Provides:
  - Health check
  - Mock perception endpoint (for testing without n8n)
  - Proxy to n8n webhooks
  - Session state (in-memory, demo only)

Run:  python server/app.py
"""

from __future__ import annotations
import os
import json
import time
import uuid
from flask import Flask, request, jsonify

app = Flask(__name__)

# ── In-memory session store (demo only) ──
sessions: dict = {}


def _now():
    return int(time.time() * 1000)


# ── Health ──
@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "ai-safepath-server"})


# ── Mock perception (for testing without n8n) ──
@app.route("/api/v1/mock/perception", methods=["POST"])
def mock_perception():
    """
    Returns a mock perception response for testing the PWA
    without connecting to n8n.

    Body: { "scenario": "pole_left" | "vehicle_stop" | "clear" | "all_blocked" | "low_conf" }
    """
    data = request.get_json(force=True, silent=True) or {}
    scenario = data.get("scenario", "clear")

    SCENARIOS = {
        "clear": {
            "scene_summary": "Open sidewalk. No obstacles.",
            "objects": [],
            "left_path": {"clear": True, "risk": "LOW", "confidence": 0.90},
            "center_path": {"clear": True, "risk": "LOW", "confidence": 0.92},
            "right_path": {"clear": True, "risk": "LOW", "confidence": 0.88},
            "overall_risk": "LOW",
            "confidence": 0.90,
        },
        "pole_left": {
            "scene_summary": "Pole ahead on sidewalk.",
            "objects": [
                {"type": "pole", "position": "center", "estimated_distance_m": 4.0,
                 "distance_confidence": 0.72, "blocks_path": True, "risk": "HIGH"},
            ],
            "left_path": {"clear": True, "risk": "LOW", "confidence": 0.88},
            "center_path": {"clear": False, "risk": "HIGH", "confidence": 0.91},
            "right_path": {"clear": False, "risk": "HIGH", "confidence": 0.75},
            "overall_risk": "HIGH",
            "confidence": 0.86,
        },
        "vehicle_stop": {
            "scene_summary": "Vehicle approaching.",
            "objects": [
                {"type": "vehicle", "position": "center", "estimated_distance_m": 6.0,
                 "distance_confidence": 0.85, "blocks_path": True, "risk": "CRITICAL"},
            ],
            "left_path": {"clear": True, "risk": "LOW", "confidence": 0.85},
            "center_path": {"clear": False, "risk": "CRITICAL", "confidence": 0.92},
            "right_path": {"clear": True, "risk": "LOW", "confidence": 0.82},
            "overall_risk": "CRITICAL",
            "confidence": 0.90,
        },
        "all_blocked": {
            "scene_summary": "All paths blocked.",
            "objects": [
                {"type": "construction_barrier", "position": "center", "estimated_distance_m": 3.0,
                 "distance_confidence": 0.80, "blocks_path": True, "risk": "CRITICAL"},
                {"type": "wall", "position": "left", "estimated_distance_m": 4.0,
                 "distance_confidence": 0.75, "blocks_path": True, "risk": "HIGH"},
            ],
            "left_path": {"clear": False, "risk": "HIGH", "confidence": 0.80},
            "center_path": {"clear": False, "risk": "CRITICAL", "confidence": 0.90},
            "right_path": {"clear": False, "risk": "HIGH", "confidence": 0.78},
            "overall_risk": "CRITICAL",
            "confidence": 0.88,
        },
        "low_conf": {
            "scene_summary": "Blurry frame.",
            "objects": [],
            "left_path": {"clear": True, "risk": "LOW", "confidence": 0.40},
            "center_path": {"clear": True, "risk": "LOW", "confidence": 0.35},
            "right_path": {"clear": True, "risk": "LOW", "confidence": 0.38},
            "overall_risk": "LOW",
            "confidence": 0.30,
        },
    }

    result = SCENARIOS.get(scenario, SCENARIOS["clear"])
    result["frame_timestamp_ms"] = _now()
    result["debug"] = {"source": "mock_server", "scenario": scenario}
    return jsonify(result)


# ── Mock safety decision (for testing) ──
@app.route("/api/v1/mock/decision", methods=["POST"])
def mock_decision():
    """Returns a mock safety decision based on a scenario."""
    data = request.get_json(force=True, silent=True) or {}
    scenario = data.get("scenario", "clear")

    SCENARIOS = {
        "clear": {"action": "STRAIGHT", "reason": "Path ahead clear.", "confidence": 0.90,
                  "voice_instruction": "Path clear. Continue straight."},
        "pole_left": {"action": "LEFT", "reason": "Pole ahead. Move left.", "confidence": 0.86,
                       "voice_instruction": "Pole ahead. Move left."},
        "vehicle_stop": {"action": "STOP", "reason": "Vehicle approaching.", "confidence": 0.90,
                          "voice_instruction": "Vehicle approaching. Stop."},
        "all_blocked": {"action": "STOP", "reason": "All paths blocked.", "confidence": 0.85,
                         "voice_instruction": "Path blocked. Stop."},
        "low_conf": {"action": "WAIT", "reason": "Low confidence.", "confidence": 0.30,
                     "voice_instruction": "Wait. Reassessing."},
    }

    result = SCENARIOS.get(scenario, SCENARIOS["clear"])
    result["timestamp"] = _now()
    result["perception_summary"] = {"overall_risk": "LOW", "primary_threat": "none", "threat_count": 0}
    return jsonify(result)


# ── Session management ──
@app.route("/api/v1/session", methods=["POST"])
def session_create():
    data = request.get_json(force=True, silent=True) or {}
    session_id = data.get("session_id") or str(uuid.uuid4())[:8]
    session = {
        "session_id": session_id,
        "origin": data.get("origin"),
        "destination": data.get("destination"),
        "current_location": data.get("current_location"),
        "heading_deg": data.get("heading_deg"),
        "route": data.get("route"),
        "status": "active",
        "last_perception": None,
        "last_decision": None,
        "last_voice_instruction": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    sessions[session_id] = session
    return jsonify(session)


@app.route("/api/v1/session/<session_id>", methods=["GET"])
def session_get(session_id):
    session = sessions.get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    return jsonify(session)


@app.route("/api/v1/session/<session_id>", methods=["POST"])
def session_update(session_id):
    session = sessions.get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    for key in ("current_location", "heading_deg", "route", "last_perception", "last_decision", "last_voice_instruction", "status"):
        if key in data:
            session[key] = data[key]
    session["updated_at"] = _now()
    return jsonify(session)


# ── Proxy to n8n (optional) ──
N8N_WEBHOOK_BASE = os.environ.get("N8N_WEBHOOK_BASE", "")

@app.route("/api/v1/n8n/<path:endpoint>", methods=["POST"])
def n8n_proxy(endpoint):
    """Proxy a request to n8n Cloud webhook."""
    if not N8N_WEBHOOK_BASE:
        return jsonify({"error": "N8N_WEBHOOK_BASE not configured"}), 503

    import requests as req_lib
    url = N8N_WEBHOOK_BASE + "/" + endpoint
    try:
        resp = req_lib.post(url, json=request.get_json(force=True), timeout=15)
        return resp.content, resp.status_code, {"Content-Type": resp.headers.get("Content-Type", "application/json")}
    except Exception as e:
        return jsonify({"error": f"Proxy failed: {str(e)}"}), 502


if __name__ == "__main__":
    port = int(os.environ.get("SERVER_PORT", 8080))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    print(f"SafePath server starting on :{port}")
    print(f"  Health:  http://localhost:{port}/health")
    print(f"  Mock perception: http://localhost:{port}/api/v1/mock/perception")
    print(f"  Mock decision:   http://localhost:{port}/api/v1/mock/decision")
    print(f"  Sessions:        http://localhost:{port}/api/v1/session")
    app.run(host="0.0.0.0", port=port, debug=debug)
