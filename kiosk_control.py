#!/usr/bin/env python3

import os
import time
import subprocess
import json
import logging
from datetime import datetime
import psutil # For process management

# --- Configuration ---
# Get the absolute path of the directory where this script is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
# --- NEW: Define a persistent user data directory ---
# This will be created in your project folder.
USER_DATA_DIR = os.path.join(BASE_DIR, 'chromium_user_data') 

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Globals ---
browser_process = None
current_url_list = []
current_tab_index = 0

# --- Helper Functions ---
def read_config():
    """Reads the config file."""
    global CONFIG_FILE
    if not os.path.exists(CONFIG_FILE):
        logging.warning("Config file not found. Using default values.")
        return {
            "on_urls": [{"url": "https://google.com", "duration": 15}],
            "off_hours_url": "https://duckduckgo.com",
            "on_hours_start": "08:00",
            "on_hours_end": "18:00"
        }
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error reading config: {e}")
        return {}

def is_on_hours(start_str, end_str):
    """Checks if the current time is within the 'on' hours."""
    try:
        now = datetime.now().time()
        start = datetime.strptime(start_str, '%H:%M').time()
        end = datetime.strptime(end_str, '%H:%M').time()

        if start <= end:
            # Normal day (e.g., 08:00 to 18:00)
            return start <= now < end
        else:
            # Overnight (e.g., 22:00 to 06:00)
            return now >= start or now < end
    except Exception as e:
        logging.error(f"Error checking time: {e}")
        return False # Default to off-hours

def kill_browser():
    """Finds and forcefully terminates any existing Chromium processes."""
    global browser_process
    
    # First, try terminating our tracked process
    if browser_process and browser_process.poll() is None:
        try:
            # Find all children of the main browser process
            parent = psutil.Process(browser_process.pid)
            children = parent.children(recursive=True)
            
            # Terminate children first
            for child in children:
                child.terminate()
            
            # Terminate the parent
            parent.terminate()
            
            # Wait a moment
            browser_process.wait(timeout=2)
            logging.info("Browser process terminated.")
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
             # Process already gone or stuck, fall back to kill
            try:
                browser_process.kill()
                logging.info("Browser process killed.")
            except Exception as e:
                logging.warning(f"Failed to kill process: {e}")
        except Exception as e:
            logging.warning(f"Error terminating process: {e}")
            
    browser_process = None

    # As a fallback, hunt for any stray 'chromium' processes
    # This is more aggressive but ensures a clean state
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            if 'chromium' in proc.info['name'].lower():
                try:
                    p = psutil.Process(proc.info['pid'])
                    p.kill()
                    logging.info(f"Killed stray Chromium process (PID: {proc.info['pid']})")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass # Process already gone or not ours
    except Exception as e:
        logging.error(f"Error during stray process cleanup: {e}")


def launch_browser(urls_to_open):
    """Launches Chromium with all specified URLs in separate tabs."""
    global browser_process, USER_DATA_DIR
    
    if not urls_to_open:
        logging.error("No URLs provided to launch.")
        return

    # Ensure the user data directory exists
    if not os.path.exists(USER_DATA_DIR):
        os.makedirs(USER_DATA_DIR)
        logging.info(f"Created user data directory at: {USER_DATA_DIR}")

    # Define the command to start Chromium
    command = [
        'chromium',
        '--kiosk',          # Kiosk mode
        '--disable-infobars', # Disable "Chrome is being controlled..."
        '--noerrdialogs',     # Suppress error dialogs
        
        # --- KEY CHANGES ---
        # 1. REMOVED: '--incognito' (This was deleting your login)
        # 2. ADDED: '--user-data-dir' (This saves your cookies/session)
        f'--user-data-dir={USER_DATA_DIR}',
        
        '--check-for-update-interval=31536000', # Don't check for updates
        '--disable-pinch',  # Disable pinch-to-zoom
        '--start-maximized',# Start maximized
    ]
    
    # Add all URLs to the command. Chromium will open each in a new tab.
    command.extend(urls_to_open)

    try:
        logging.info(f"Launching Chromium with {len(urls_to_open)} URLs...")
        # Use Popen to launch without blocking
        browser_process = subprocess.Popen(command, env=os.environ)
        
        # Give the browser time to start and open all tabs
        time.sleep(10) # Increased to 10s for multiple tabs to load
        
        # Focus the first tab (Ctrl+1)
        focus_tab(1)
        
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")

def focus_tab(tab_index):
    """Uses xdotool to focus a specific browser tab (1-indexed)."""
    try:
        # xdotool key 'ctrl+<index>'
        subprocess.run(['xdotool', 'key', f'ctrl+{tab_index}'], check=True)
    except Exception as e:
        logging.error(f"Failed to focus tab {tab_index}: {e}")

def cycle_to_next_tab():
    """Uses xdotool to cycle to the next tab (Ctrl+Tab)."""
    try:
        subprocess.run(['xdotool', 'key', 'ctrl+Tab'], check=True)
    except Exception as e:
        logging.error(f"Failed to cycle tabs: {e}")

# --- Main Kiosk Loop ---
def main_loop():
    global current_url_list, current_tab_index, browser_process
    last_mode = None
    last_config = None

    while True:
        try:
            # 1. Read Config
            config = read_config()
            
            # Check if config is valid
            if not config.get("on_urls") or not config.get("off_hours_url"):
                logging.error("Config is invalid or missing keys. Retrying in 30s.")
                time.sleep(30)
                continue
                
            # 2. Determine Mode (On or Off)
            is_on = is_on_hours(config["on_hours_start"], config["on_hours_end"])
            current_mode = "ON" if is_on else "OFF"
            
            # 3. Check for Mode or Config Change
            # If mode changed (e.g., ON->OFF) or config file itself changed,
            # we must restart the browser with the new URL list.
            if current_mode != last_mode or config != last_config:
                logging.info(f"Mode change detected. Entering {current_mode} hours mode.")
                
                # Kill any existing browser
                kill_browser() 
                
                # Prepare new URL list
                if is_on:
                    current_url_list = config.get("on_urls", [])
                    urls_to_launch = [entry["url"] for entry in current_url_list]
                else:
                    # Off hours, just one URL
                    current_url_list = [{"url": config["off_hours_url"], "duration": 3600}] # Fake long duration
                    urls_to_launch = [config["off_hours_url"]]
                
                # Reset tab index and launch new browser
                current_tab_index = 0
                if urls_to_launch:
                    launch_browser(urls_to_launch)
                else:
                    logging.error("No URLs to launch for current mode.")

                last_mode = current_mode
                last_config = config
                
                # After launching, no need to sleep, just continue to next loop iteration
                # to get the duration for the first tab
                continue 
            
            # 4. Handle Tab Rotation (if in ON-hours)
            if is_on and current_url_list:
                # Ensure browser is still running. If not, the loop will restart it.
                if browser_process is None or browser_process.poll() is not None:
                    logging.warning("Browser process not running. Forcing restart.")
                    last_mode = None # Force a full restart on next loop
                    time.sleep(5)
                    continue

                # Get current tab's info
                current_tab_info = current_url_list[current_tab_index]
                duration = current_tab_info.get("duration", 15)
                
                logging.info(f"Displaying Tab {current_tab_index + 1} ({current_tab_info['url']}) for {duration}s")
                
                # Wait for the specified duration
                time.sleep(duration)
                
                # Move to the next tab
                current_tab_index = (current_tab_index + 1) % len(current_url_list)
                
                # Focus the next tab. xdotool is 1-indexed.
                focus_tab(current_tab_index + 1)

            else:
                # We are in OFF-hours, just sleep for a while.
                # The browser is already on the correct single page.
                logging.info("In Off-Hours mode. Checking again in 60s.")
                time.sleep(60)

        except KeyboardInterrupt:
            logging.info("Kiosk script stopped by user.")
            kill_browser()
            break
        except Exception as e:
            logging.error(f"Unhandled error in main loop: {e}. Restarting loop in 15s.")
            kill_browser()
            last_mode = None # Force full restart
            time.sleep(15)

if __name__ == "__main__":
    logging.info("Starting Kiosk Control Script...")
    # Clean up any old processes before starting
    kill_browser() 
    time.sleep(1) # Short pause
    main_loop()

