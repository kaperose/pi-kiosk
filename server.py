#!/usr/bin/env python3

import os
import json
import subprocess
import logging
from flask import Flask, request, jsonify, render_template, send_from_directory

# --- Configuration ---
# Get the absolute path of the directory where this script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
STATIC_DIR = os.path.join(BASE_DIR, 'static')

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__, template_folder=BASE_DIR, static_folder=STATIC_DIR)

# --- Helper Function ---
def read_config():
    """Reads the config file."""
    if not os.path.exists(CONFIG_FILE):
        logging.warning("Config file not found, creating default.")
        default_config = {
            "on_urls": [{"url": "https://google.com", "duration": 60}],
            "off_hours_url": "https://duckduckgo.com",
            "on_hours_start": "08:00",
            "on_hours_end": "18:00"
        }
        write_config(default_config)
        return default_config
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error reading config: {e}")
        return {}

def write_config(config_data):
    """Writes to the config file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=4)
        return True
    except Exception as e:
        logging.error(f"Error writing config: {e}")
        return False

# --- Web Routes ---

@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('index.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serves static files (like style.css)."""
    return send_from_directory(app.static_folder, filename)

# --- API Routes ---

@app.route('/api/config', methods=['GET'])
def api_get_config():
    """Gets the current configuration."""
    config = read_config()
    return jsonify(config)

@app.route('/api/config', methods=['POST'])
def api_set_config():
    """Saves a new configuration."""
    config_data = request.json
    if write_config(config_data):
        return jsonify({"message": "Configuration saved successfully."}), 200
    else:
        return jsonify({"message": "Failed to write configuration."}), 500

@app.route('/api/restart', methods=['POST'])
def api_restart():
    """Restarts only the kiosk display service."""
    try:
        # Note: This requires the sudoers setup to work
        cmd = ['sudo', '/bin/systemctl', 'restart', 'kiosk-display.service']
        subprocess.run(cmd, check=True)
        return jsonify({"message": "Kiosk display is restarting."}), 200
    except subprocess.CalledProcessError as e:
        error_message = f"Restart command failed: {e.stderr}"
        logging.error(error_message)
        return jsonify({"message": error_message, "details": e.stderr}), 500
    except Exception as e:
        logging.error(f"Unexpected error during restart: {str(e)}")
        return jsonify({"message": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/api/update', methods=['POST'])
def api_update():
    """Pulls updates from Git and restarts the display service."""
    try:
        # Run git pull. This needs the sudoers file to be correct.
        # This command runs 'git pull' as the user 'pi' (or your user)
        # We use the full path '/usr/bin/git' for security, as defined in sudoers.
        pull_cmd = ['sudo', '/usr/bin/git', 'pull']
        git_process = subprocess.run(pull_cmd, cwd=BASE_DIR, capture_output=True, text=True, check=True)
        
        # If pull is successful, restart ONLY the display service.
        # **REMOVED** the line that restarts 'kiosk-web.service' to prevent the "Failed to fetch" error.
        subprocess.run(['sudo', '/bin/systemctl', 'restart', 'kiosk-display.service'], check=True)
        
        return jsonify({"message": "Update successful. Kiosk display is restarting.", "details": git_process.stdout}), 200
    
    except subprocess.CalledProcessError as e:
        # This catches errors from git pull or systemctl
        error_message = f"Update command failed with error: {e.stderr.strip()}"
        logging.error(error_message)
        return jsonify({"message": error_message, "details": e.stderr.strip()}), 500
    except Exception as e:
        # Catch-all for other errors
        logging.error(f"Unexpected error during update: {str(e)}")
        return jsonify({"message": f"An unexpected error occurred: {str(e)}"}), 500

# --- Main ---
if __name__ == '__main__':
    # We must run on 0.0.0.0 to be accessible on the network
    # We use port 8080 to avoid needing root to run the server
    app.run(debug=True, host='0.0.0.0', port=8080)

