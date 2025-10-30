#!/usr/bin/env python3

from flask import Flask, render_template, request, jsonify, send_from_directory
import json
import os

app = Flask(__name__, template_folder='.')

# Get the absolute path of the directory where this script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
STATIC_DIR = os.path.join(BASE_DIR, 'static') # Define static folder path

# --- Helper Functions ---

def load_config():
    """Loads the configuration from config.json"""
    if not os.path.exists(CONFIG_FILE):
        # Create a default config if it doesn't exist
        default_config = {
            "on_urls": ["https://google.com"],
            "off_hours_url": "https://duckduckgo.com",
            "rotation_time_seconds": 60,
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
        return load_config() # This will trigger the default creation

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

# --- Static File Route ---

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serves static files from the 'static' directory."""
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
    app.run(host='0.0.0.0', port=8080, debug=True)

