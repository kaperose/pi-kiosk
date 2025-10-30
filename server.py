#!/usr/bin/env python3

from flask import Flask, render_template, request, jsonify, send_from_directory
import json
import os
import subprocess

app = Flask(__name__, template_folder='.')

# Get the absolute path of the directory where this script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
# --- ADDED BACK: Define static folder path ---
STATIC_DIR = os.path.join(BASE_DIR, 'static') 

# --- Helper Functions ---

def load_config():
    """Loads the configuration from config.json"""
    if not os.path.exists(CONFIG_FILE):
        # Create a default config if it doesn't exist
        default_config = {
            "on_urls": [{"url": "https://google.com", "duration": 60}],
            "off_hours_url": "https://duckduckgo.com",
            "on_hours_start": "08:00",
            "on_hours_end": "18:00"
        }
        save_config(default_config)
        return default_config
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        # If file is corrupt, create a new default one
        # Note: This recursive call could be risky, but OK for this scope
        default_config = {
            "on_urls": [{"url": "https://google.com", "duration": 60}],
            "off_hours_url": "https://duckduckgo.com",
            "on_hours_start": "08:00",
            "on_hours_end": "18:00"
        }
        save_config(default_config)
        return default_config

def save_config(config_data):
    """Saves the configuration to config.json"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config_data, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False

# --- API Routes ---

@app.route('/api/config', methods=['GET'])
def get_config():
    """API endpoint to get the current configuration."""
    return jsonify(load_config())

@app.route('/api/config', methods=['POST'])
def set_config():
    """API endpoint to update the configuration."""
    data = request.json
    if save_config(data):
        return jsonify({"status": "success", "message": "Configuration saved."})
    else:
        return jsonify({"status": "error", "message": "Failed to save configuration."}), 500
# --- NEW: Kiosk Control API Routes ---

@app.route('/api/restart', methods=['POST'])
def restart_kiosk():
    """API endpoint to restart the kiosk display service."""
    try:
        # Run the command with sudo. This requires passwordless sudo setup.
        result = subprocess.run(
            ['sudo', '/bin/systemctl', 'restart', 'kiosk-display.service'],
            capture_output=True, text=True, check=True
        )
        return jsonify({"status": "success", "message": result.stdout})
    except subprocess.CalledProcessError as e:
        return jsonify({"status": "error", "message": f"Failed to restart: {e.stderr}"}), 500
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "Command 'sudo' or 'systemctl' not found."}), 500

@app.route('/api/update', methods=['POST'])
def update_from_github():
    """API endpoint to pull updates from GitHub and restart services."""
    try:
        # Change to the kiosk directory and run git pull
        # Using '&&' is a shell construct, so we need shell=True or run commands separately
        # A safer way is to set the 'cwd' (current working directory) for git pull
        
        git_pull = subprocess.run(
            ['git', 'pull', 'origin', 'master'], # Assuming 'master' branch
            cwd=BASE_DIR, capture_output=True, text=True, check=True
        )
        
        # Restart both services
        subprocess.run(
            ['sudo', '/bin/systemctl', 'restart', 'kiosk-web.service'],
            check=True
        )
        subprocess.run(
            ['sudo', '/bin/systemctl', 'restart', 'kiosk-display.service'],
            check=True
        )
        
        return jsonify({"status": "success", "message": f"Git pull output: {git_pull.stdout}"})
    except subprocess.CalledProcessError as e:
        error_output = e.stderr or e.stdout
        return jsonify({"status": "error", "message": f"Update failed: {error_output}"}), 500
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "Command 'git' or 'systemctl' not found."}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": f"An unexpected error occurred: {str(e)}"}), 500


# --- ADDED BACK: Static File Route ---
@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serves static files from the 'static' directory."""
    if not os.path.exists(STATIC_DIR):
        os.makedirs(STATIC_DIR)
    return send_from_directory(STATIC_DIR, filename)

# --- Frontend Route ---

@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('index.html')

if __name__ == '__main__':
    # Make sure the static directory exists
    if not os.path.exists(STATIC_DIR):
        os.makedirs(STATIC_DIR)
        
    print(f"Web interface running on http://0.0.0.0:8080")
    print(f"Serving static files from: {STATIC_DIR}")
    app.run(host='0.0.0.0', port=8080, debug=False) # Turn off debug mode for production

