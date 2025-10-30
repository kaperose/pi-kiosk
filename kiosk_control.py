#!/usr/bin/env python3

import subprocess
import time
import json
import os
import psutil
import logging # <-- Added this import
from datetime import datetime

# --- Configuration ---
# Get the absolute path of the directory where this script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Helper Functions ---

def load_config():
    """Loads the configuration from config.json"""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        logging.info("Configuration loaded successfully.")
        return config
    except Exception as e:
        logging.error(f"Error loading config: {e}. Using default values.")
        # Default fallback config
        return {
            "on_urls": ["https://google.com"],
            "off_hours_url": "https://duckduckgo.com",
            "rotation_time_seconds": 60,
            "on_hours_start": "08:00",
            "on_hours_end": "18:00"
        }

def is_on_hours(config):
    """Checks if the current time is within the 'on' hours"""
    try:
        now = datetime.now().time()
        start = datetime.strptime(config['on_hours_start'], '%H:%M').time()
        end = datetime.strptime(config['on_hours_end'], '%H:%M').time()

        if start <= end:
            return start <= now <= end
        else: # Handles overnight schedules (e.g., 22:00 to 06:00)
            return start <= now or now <= end
    except Exception as e:
        logging.error(f"Error checking time: {e}")
        return False

def kill_chromium():
    """Finds and terminates all running chromium-browser processes."""
    logging.debug("Attempting to kill existing Chromium processes...")
    for proc in psutil.process_iter(['pid', 'name']):
        if 'chromium' in proc.info['name'].lower():
            try:
                proc.kill()
                logging.info(f"Killed existing Chromium process (PID: {proc.info['pid']})")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                logging.debug(f"Could not kill process {proc.info.get('pid', 'N/A')}.")
                pass
    # Give a moment for processes to terminate
    time.sleep(1)

def launch_chromium(url):
    """Lauches Chromium in kiosk mode."""
    logging.info(f"Launching Chromium with URL: {url}")
    
    # Define the command to start Chromium
    command = [
        'chromium',  # Changed from 'chromium-browser'
        '--kiosk',
        '--disable-infobars',
        '--noerrdialogs',
        '--incognito',
        '--check-for-update-interval=31536000',
        url
    ]
    # Use Popen to launch without blocking
    try:
        subprocess.Popen(command, env=os.environ) # <-- Fixed variable name from 'cmd' to 'command'
    except FileNotFoundError:
        logging.error("CRITICAL: 'chromium' command not found. Make sure it is installed and in your PATH.")
    except Exception as e:
        logging.error(f"Failed to launch Chromium: {e}")

# --- Main Kiosk Loop ---

def main():
    logging.info("Starting Kiosk Control Script...")
    current_url = None
    current_mode = None # 'on' or 'off'
    url_index = 0

    while True:
        try:
            config = load_config()
            on_hours = is_on_hours(config)

            if on_hours:
                # --- ON HOURS LOGIC ---
                if current_mode != 'on' or not config['on_urls']:
                    # Switching to 'on' mode or URL list is empty
                    logging.info("Entering ON hours mode.")
                    kill_chromium()
                    current_mode = 'on'
                    url_index = 0
                    
                if not config['on_urls']:
                    logging.warning("On hours, but on_urls list is empty. Sleeping.")
                    time.sleep(30) # Check again in 30s
                    continue

                # Get the next URL
                url_to_show = config['on_urls'][url_index]
                
                if url_to_show != current_url:
                    logging.info(f"Changing URL to: {url_to_show}")
                    kill_chromium()
                    launch_chromium(url_to_show)
                    current_url = url_to_show
                
                # Increment index for next rotation
                url_index = (url_index + 1) % len(config['on_urls'])
                
                # Wait for the rotation time
                rotation_seconds = config.get('rotation_time_seconds', 60)
                logging.info(f"Displaying {current_url} for {rotation_seconds}s")
                time.sleep(rotation_seconds)

            else:
                # --- OFF HOURS LOGIC ---
                url_to_show = config['off_hours_url']
                
                if current_mode != 'off' or current_url != url_to_show:
                    logging.info(f"Entering OFF hours mode. Displaying: {url_to_show}")
                    kill_chromium()
                    current_mode = 'off'
                    launch_chromium(url_to_show)
                    current_url = url_to_show
                
                # In off-hours, just sleep and re-check periodically
                logging.debug(f"Off hours. Displaying {current_url}. Re-checking in 60s.")
                time.sleep(60)

        except KeyboardInterrupt:
            logging.info("Kiosk script stopped by user.")
            kill_chromium()
            break
        except Exception as e:
            logging.error(f"An unexpected error occurred in main loop: {e}", exc_info=True)
            kill_chromium() # Kill browser on error
            time.sleep(10) # Wait before retrying

if __name__ == "__main__":
    main()

