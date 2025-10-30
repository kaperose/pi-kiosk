#!/usr/bin/env python3

import subprocess
import time
import json
import os
import psutil
import logging
from datetime import datetime

# --- Configuration ---
# Get the absolute path of the directory where this script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Global process variable
browser_process = None

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
            "on_urls": [{"url": "https://google.com", "duration": 60}],
            "off_hours_url": "https://duckduckgo.com",
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
    global browser_process
    if browser_process:
        logging.info("Terminating existing Chromium process.")
        try:
            # Get all children of the main process (includes all tabs)
            parent = psutil.Process(browser_process.pid)
            children = parent.children(recursive=True)
            for child in children:
                child.kill()
            parent.kill()
            browser_process.wait(timeout=5)
            logging.info("Chromium terminated.")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired, psutil.ZombieProcess):
            logging.debug("Could not cleanly terminate process, or it was already dead.")
            pass
    
    # Fallback: Find and terminate all running chromium processes by name
    # This is a bit more aggressive but ensures a clean state
    logging.debug("Running fallback process kill by name...")
    for proc in psutil.process_iter(['pid', 'name']):
        if 'chromium' in proc.info['name'].lower():
            try:
                psutil.Process(proc.info['pid']).kill()
                logging.info(f"Killed lingering Chromium process (PID: {proc.info['pid']})")
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                logging.debug(f"Could not kill process {proc.info.get('pid', 'N/A')}.")
                pass
    browser_process = None
    time.sleep(1) # Give a moment for processes to terminate

def launch_chromium(url_objects_list):
    """Lauches Chromium in kiosk mode with one or more URLs."""
    global browser_process
    kill_chromium() # Ensure no old instances are running
    
    # Extract URLs from the list of objects
    urls_list = [item.get('url', 'about:blank') for item in url_objects_list if item.get('url')]
    
    if not urls_list:
        logging.warning("Launch_chromium called, but no valid URLs were provided.")
        return
        
    logging.info(f"Launching Chromium with {len(urls_list)} URL(s).")
    
    # All URLs are passed as arguments at the end
    command = [
        'chromium',
        '--kiosk',
        '--disable-infobars',
        '--noerrdialogs',
        '--incognito',
        '--check-for-update-interval=31536000',
    ] + urls_list
    
    try:
        # Use Popen to launch without blocking
        # We pass the full command, including all URLs
        browser_process = subprocess.Popen(command, env=os.environ)
        logging.info(f"Chromium process started with PID: {browser_process.pid}")
        # Give the browser time to open all tabs
        time.sleep(10) 
    except FileNotFoundError:
        logging.error("CRITICAL: 'chromium' command not found. Make sure it is installed and in your PATH.")
    except Exception as e:
        logging.error(f"Failed to launch Chromium: {e}")

def switch_to_next_tab():
    """Uses xdotool to simulate a 'Ctrl+Tab' keypress to switch tabs."""
    try:
        logging.debug("Switching to next tab (Ctrl+Tab)")
        # 'key' command simulates key press and release
        subprocess.run(['xdotool', 'key', 'ctrl+Tab'], check=True, env=os.environ)
    except FileNotFoundError:
        logging.error("CRITICAL: 'xdotool' command not found. Please install it with 'sudo apt-get install xdotool'")
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to switch tabs using xdotool: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred during tab switch: {e}")


# --- Main Kiosk Loop ---

def main():
    logging.info("Starting Kiosk Control Script...")
    current_mode = None # 'on' or 'off'
    last_config = None
    url_index = 0 # Keep track of the current tab index

    while True:
        try:
            config = load_config()
            on_hours = is_on_hours(config)
            
            # Detect if config has changed, easier than full state check
            config_changed = (config != last_config)
            last_config = config

            if on_hours:
                # --- ON HOURS LOGIC ---
                # We need to relaunch if:
                # 1. We are just switching from 'off' mode
                # 2. The configuration has changed
                if current_mode != 'on' or config_changed:
                    logging.info("Entering ON hours mode or config changed.")
                    if not config.get('on_urls'):
                        logging.warning("On hours, but on_urls list is empty. Killing browser.")
                        kill_chromium()
                        current_mode = 'on'
                    else:
                        launch_chromium(config['on_urls'])
                        current_mode = 'on'
                        url_index = 0 # Reset index on launch
                
                # If we are already in 'on' mode and config is same, just rotate tabs
                elif current_mode == 'on' and config.get('on_urls'):
                    
                    if not config['on_urls']:
                        logging.debug("On hours, but no URLs to display. Sleeping.")
                        time.sleep(60)
                        continue
                    
                    # Ensure index is valid
                    if url_index >= len(config['on_urls']):
                        url_index = 0
                        
                    # Get current item's config
                    current_item = config['on_urls'][url_index]
                    url_to_show = current_item.get('url', 'about:blank')
                    duration = int(current_item.get('duration', 60))

                    logging.info(f"Displaying {url_to_show} for {duration}s (Tab {url_index + 1}/{len(config['on_urls'])})")
                    time.sleep(duration)
                    
                    # Only switch tab if there is more than one
                    if len(config['on_urls']) > 1:
                        switch_to_next_tab()
                        url_index = (url_index + 1) % len(config['on_urls'])
                
                else:
                    # On hours, but no URLs. Just wait.
                    logging.debug("On hours, but no URLs to display. Sleeping.")
                    time.sleep(60)

            else:
                # --- OFF HOURS LOGIC ---
                url_to_show = config['off_hours_url']
                
                # We need to relaunch if:
                # 1. We are just switching from 'on' mode
                # 2. The configuration has changed
                if current_mode != 'off' or config_changed:
                    logging.info(f"Entering OFF hours mode. Displaying: {url_to_show}")
                    launch_chromium([{"url": url_to_show, "duration": 0}]) # Pass as a list of one object
                    current_mode = 'off'
                
                # In off-hours, just sleep and re-check periodically
                logging.debug(f"Off hours. Displaying {url_to_show}. Re-checking in 60s.")
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



