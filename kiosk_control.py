import subprocess
import time
import json
import logging
from datetime import datetime
import os
import psutil

# --- Configuration ---
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')
LOG_FILE = os.path.join(os.path.dirname(__file__), 'kiosk.log')
# --- End Configuration ---

# --- Setup Logging ---
# Clear the log file on each start
try:
    with open(LOG_FILE, 'w'):
        pass
except IOError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ])
# --- End Setup Logging ---

# --- Global State ---
browser_process = None
current_url_index = 0
current_mode = None  # 'ON' or 'OFF'
# --- End Global State ---

def load_config():
    """Loads the configuration from config.json."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        logging.info("Configuration loaded successfully.")
        return config
    except Exception as e:
        logging.error(f"FATAL: Could not load config file: {e}")
        return None

def is_on_hours(start_str, end_str):
    """Checks if the current time is within the 'on hours'."""
    try:
        now = datetime.now().time()
        start_time = datetime.strptime(start_str, '%H:%M').time()
        end_time = datetime.strptime(end_str, '%H:%M').time()

        if start_time <= end_time:
            # Normal day (e.g., 08:00 to 18:00)
            return start_time <= now < end_time
        else:
            # Overnight (e.g., 22:00 to 06:00)
            return now >= start_time or now < end_time
    except Exception as e:
        logging.error(f"Error in time check: {e}")
        return False

def kill_browser():
    """Finds and terminates any existing Chromium process and its children."""
    global browser_process
    
    if browser_process and browser_process.poll() is None:
        logging.info(f"Terminating existing browser process (PID: {browser_process.pid}).")
        try:
            # Get all children of the main process
            parent = psutil.Process(browser_process.pid)
            children = parent.children(recursive=True)
            
            # Terminate children first
            for child in children:
                child.terminate()
            
            # Terminate the parent
            parent.terminate()
            
            # Wait for processes to die
            gone, alive = psutil.wait_procs([parent] + children, timeout=3)
            
            # Force kill any stubborn processes
            for p in alive:
                logging.warning(f"Process {p.pid} did not terminate, force killing.")
                p.kill()
                
        except psutil.NoSuchProcess:
            logging.info(f"Process {browser_process.pid} already gone.")
        except Exception as e:
            logging.error(f"Error during process termination: {e}")
    
    browser_process = None
    logging.info("Browser process terminated.")

def launch_browser(urls):
    """Launches Chromium with the specified URLs, one per tab."""
    global browser_process
    kill_browser()  # Ensure no old browser is running

    if not urls:
        logging.error("No URLs provided to launch.")
        return

    # Use a persistent user data directory to save sessions/cookies
    # THIS IS THE FIX for the login prompt
    user_data_dir = os.path.expanduser("~/.config/chromium_kiosk_profile")
    
    command = [
        'chromium',
        '--kiosk',
        '--disable-infobars',
        '--noerrdialogs',
        '--check-for-update-interval=31536000',
        '--disable-features=Translate',
        f'--user-data-dir={user_data_dir}' # THIS IS THE FIX
        # '--incognito' flag was REMOVED
    ] + urls  # Add all URLs as arguments

    logging.info(f"Launching new browser session with {len(urls)} tabs.")
    try:
        # Use Popen to launch without blocking
        browser_process = subprocess.Popen(
            command, 
            env=os.environ.copy(),
            preexec_fn=os.setsid  # Start in a new session
        )
        logging.info(f"Browser launched with PID: {browser_process.pid}")
        # Give the browser time to open all tabs
        time.sleep(10) 
    except Exception as e:
        logging.error(f"Failed to launch browser: {e}")
        browser_process = None

def switch_to_tab(tab_index):
    """Switches to a specific tab index (1-based)."""
    try:
        # `xdotool` needs DISPLAY, which is set in the .service file
        # Using 'Ctrl+Page_Down' to cycle
        logging.info(f"Switching to next tab...")
        subprocess.run(
            ['xdotool', 'search', '--onlyvisible', '--class', 'chromium', 'windowactivate', '--sync', 'key', 'Ctrl+Page_Down'],
            check=True,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        logging.warning(f"Failed to switch tab: {e.stderr}")
    except Exception as e:
        logging.error(f"Error during tab switch: {e}")

# --- Main Kiosk Loop ---
def main():
    global current_mode, current_url_index

    logging.info("--- Kiosk Control Script Started ---")
    
    while True:
        config = load_config()
        if not config:
            logging.error("Retrying config load in 60s...")
            time.sleep(60)
            continue
        
        on_urls = config.get('on_urls', [])
        off_url = config.get('off_hours_url')
        
        on = is_on_hours(config.get('on_hours_start'), config.get('on_hours_end'))
        
        if on:
            # --- ON HOURS ---
            if current_mode != 'ON' or browser_process is None or browser_process.poll() is not None:
                logging.info("Entering 'On Hours' mode.")
                current_mode = 'ON'
                current_url_index = 0
                
                urls_to_launch = [entry['url'] for entry in on_urls if entry.get('url')]
                if not urls_to_launch:
                    logging.warning("'On Hours' mode active, but no URLs are configured. Waiting.")
                    time.sleep(60) # THIS IS THE FIX (was outside the loop)
                    continue
                
                launch_browser(urls_to_launch)
            
            # --- Tab Switching Logic ---
            if on_urls and len(on_urls) > 0:
                if current_url_index >= len(on_urls):
                    current_url_index = 0 # Loop back to the start
                
                # Get the duration for the current tab
                current_entry = on_urls[current_url_index]
                duration = current_entry.get('duration', 60)
                
                logging.info(f"Displaying tab {current_url_index + 1} ({current_entry.get('notes', 'No notes')}) for {duration}s")
                
                # Switch to the tab (if more than one)
                if len(on_urls) > 1:
                    switch_to_tab(current_url_index + 1)
                
                # Wait for the specified duration
                # THIS IS THE FIX for the duration bug
                time.sleep(duration) 
                
                # Move to the next tab index for the next loop
                current_url_index += 1
            else:
                # No URLs, just wait
                time.sleep(60)

        else:
            # --- OFF HOURS ---
            if current_mode != 'OFF' or browser_process is None or browser_process.poll() is not None:
                logging.info("Entering 'Off Hours' mode.")
                current_mode = 'OFF'
                if not off_url:
                    logging.warning("'Off Hours' mode active, but no off-hours URL is configured. Killing browser.")
                    kill_browser()
                else:
                    launch_browser([off_url])
            
            # In off-hours, just sleep and re-check the time
            time.sleep(60)
        
        # The main 'sleep' was REMOVED from here to allow custom durations

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Script stopped by user (KeyboardInterrupt).")
        kill_browser()
    except Exception as e:
        logging.error(f"--- UNHANDLED EXCEPTION: {e} ---")
        kill_browser()

