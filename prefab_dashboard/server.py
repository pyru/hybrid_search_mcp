"""
Prefab Dashboard server — http://localhost:5050

  GET  /            → dashboard HTML
  GET  /api/data    → JSON feed (polled every 3 s by the UI)
  POST /api/query   → save user query {"query": "..."}
  POST /api/reset   → clear all cards and activity
"""
import json
from pathlib import Path

from flask import Flask, jsonify, render_template, request

BASE_DIR  = Path(__file__).parent
DATA_FILE = BASE_DIR / "data" / "dashboard.json"

app = Flask(__name__, template_folder="templates")

_EMPTY = {"cards": [], "activity_log": [], "last_updated": None, "current_query": ""}


def _read() -> dict:
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return dict(_EMPTY)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/data")
def get_data():
    return jsonify(_read())


@app.route("/api/query", methods=["POST"])
def set_query():
    body = request.get_json(force=True, silent=True) or {}
    query = str(body.get("query", "")).strip()
    data = _read()
    data["current_query"] = query
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return jsonify({"status": "ok", "query": query})


@app.route("/api/reset", methods=["POST"])
def reset():
    DATA_FILE.write_text(json.dumps(_EMPTY, indent=2), encoding="utf-8")
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        DATA_FILE.write_text(json.dumps(_EMPTY, indent=2), encoding="utf-8")
    print("Prefab Dashboard running at http://localhost:5050")
    app.run(host="0.0.0.0", port=5050, debug=False)
