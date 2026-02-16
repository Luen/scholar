import json
import os
import re

from flask import Flask, jsonify, send_from_directory

app = Flask(__name__)

SCHOLAR_DATA_DIR = os.environ.get("SCHOLAR_DATA_DIR", "scholar_data")
SCHOLAR_DATA_DIR_ABS = os.path.abspath(SCHOLAR_DATA_DIR)


def _scholar_file_path(scholar_id: str) -> str | None:
    """Return safe path to scholar JSON file, or None if invalid."""
    if len(scholar_id) != 12 or not re.match(r"^[a-zA-Z0-9_-]+$", scholar_id):
        return None
    path = os.path.join(SCHOLAR_DATA_DIR_ABS, f"{scholar_id}.json")
    # Ensure path stays inside SCHOLAR_DATA_DIR (path traversal safety)
    try:
        real_path = os.path.realpath(path)
        if os.path.commonpath([real_path, SCHOLAR_DATA_DIR_ABS]) != SCHOLAR_DATA_DIR_ABS:
            return None
    except (ValueError, OSError):
        return None
    return real_path


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy"}), 200


@app.route("/favicon.ico", methods=["GET"])
def favicon():
    """Serve favicon if present in project root."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    favicon_path = os.path.join(root, "favicon.ico")
    if os.path.isfile(favicon_path):
        return send_from_directory(root, "favicon.ico")
    return "", 204  # No content


@app.route("/", methods=["GET"])
def index():
    return "Welcome to the scholarly API"


@app.route("/scholars", methods=["GET"])
def list_scholars():
    """List available scholar IDs with JSON data."""
    if not os.path.isdir(SCHOLAR_DATA_DIR_ABS):
        return jsonify({"scholars": []}), 200
    try:
        ids = [
            f.replace(".json", "")
            for f in os.listdir(SCHOLAR_DATA_DIR_ABS)
            if f.endswith(".json")
        ]
        return jsonify({"scholars": sorted(ids)}), 200
    except OSError:
        return jsonify({"error": "Could not list scholars"}), 500


@app.route("/scholar/<id>", methods=["GET"])
def get_scholar(id):
    """Get scholar data by ID."""
    if not id:
        return jsonify({"error": "Missing id"}), 400
    filepath = _scholar_file_path(id)
    if not filepath:
        return jsonify({"error": "Invalid id"}), 400
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({"error": "Author not found"}), 404
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid scholar data"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
