import os
import json
from flask import Flask, jsonify, send_from_directory
import re

app = Flask(__name__)

@app.route("/favicon.ico", methods=["GET"])
def favicon():
    try:
        return send_from_directory(
            os.path.join(os.path.dirname(app.root_path), ""), "favicon.ico"
        )
    except Exception as e:
        print(e)
        return "An internal error has occurred!"

@app.route("/", methods=["GET"])
def index():
    return "Welcome to the scholarly API"

@app.route("/scholar/<id>", methods=["GET"])
def search_author_id(id):
    if id != "ynWS968AAAAJ":
        return jsonify({"error": "Author not found"}), 400
    if not id:
        return jsonify({"error": "Missing id"}), 400
    if len(id) != 12 or not re.match("^[a-zA-Z0-9_-]+$", id):
        return jsonify({"error": "Invalid id"}), 400
    try:
        with open(os.path.join("scholar_data", f"{id}.json"), "r") as f:
            data = json.load(f)
            return jsonify(data)
    except FileNotFoundError:
        return jsonify({"error": "Author not found"}), 404

if __name__ == "__main__":
    app.run(debug=False, port=8000)