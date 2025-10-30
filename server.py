#!/usr/bin/env python3

import json
import os
from flask import Flask, request, jsonify, send_from_directory, render_template_string

# --- Configuration ---
# Get the absolute path of the directory where this script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
HTML_FILE = os.path.join(BASE_DIR, 'index.html')

app = Flask(__name__)

# --- API Endpoints ---

@app.route('/')
def index():
    """Serves the main index.html file."""
    try:
        # We use render_template_string to serve the file from the same directory
        return render_template_string(open(HTML_FILE).read())
    except FileNotFoundError:
        return "Error: index.html not found.", 404

@app.route('/config', methods=['GET'])
def get_config():
    """Provides the current configuration as JSON."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        return jsonify(config)
    except Exception as e:
        print(f"Error reading config: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/config', methods=['POST'])
def set_config():
    """Updates the configuration file from posted JSON data."""
    try:
        data = request.json
        
        # Basic validation
        if not all(k in data for k in ['on_urls', 'off_hours_url', 'rotation_time_seconds', 'on_hours_start', 'on_hours_end']):
            return jsonify({"error": "Missing required fields"}), 400
            
        # Convert rotation time to int
        data['rotation_time_seconds'] = int(data['rotation_time_seconds'])

        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f, indent=4)
            
        print(f"Config updated successfully: {data}")
        return jsonify({"success": True, "config": data})
    except Exception as e:
        print(f"Error writing config: {e}")
        return jsonify({"error": str(e)}), 500

# --- Run Server ---

if __name__ == '__main__':
    print(f"Starting web server on http://0.0.0.0:8080")
    print("Access this from another computer using http://<pi-ip-address>:8080")
    app.run(host='0.0.0.0', port=8080, debug=True)
