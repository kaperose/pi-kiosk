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
url_refresh_times = {} # Dictionary to store last refresh time for each URL
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

    # Use the DEFAULT chromium user profile, which has the login cookies
    # This fixes the login prompt issue.
    user_data_dir = os.path.expanduser("~/.config/chromium")
    
    command = [
        'chromium',
        '--kiosk',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-infobars',
        '--noerrdialogs',
        '--check-for-update-interval=31536000',
        '--disable-features=Translate',
        # Force resolution and fullscreen to prevent "Small Window" issue
        '--window-size=1920,1080',
        '--start-fullscreen',
        f'--user-data-dir={user_data_dir}' 
    ] + urls

    logging.info(f"Launching new browser session with {len(urls)} tabs.")
    try:
        # Use Popen to launch without blocking
        browser_process = subprocess.Popen(
            command, 
            env=os.environ.copy(),
            preexec_fn=os.setsid  # Start in a new session
        )
        logging.info(f"Browser launched with PID: {browser_process.pid}")
        # Give the browser plenty of time to open all tabs
        time.sleep(15) 
        
        # Ensure first tab is focused
        focus_tab(1)
        
        # Initialize refresh times for all URLs
        current_time = time.time()
        for url in urls:
             url_refresh_times[url] = current_time

    except Exception as e:
        logging.error(f"Failed to launch browser: {e}")
        browser_process = None

def focus_tab(tab_index):
    """Focuses a specific tab using xdotool key shortcuts (Ctrl+1..9)."""
    try:
        if tab_index <= 8:
            key = f"ctrl+{tab_index}"
        else:
            logging.warning(f"Cannot focus tab {tab_index} directly (max 8).")
            return

        subprocess.run(['xdotool', 'key', key], check=False)
    except Exception as e:
        logging.error(f"Error focusing tab {tab_index}: {e}")

def cycle_next_tab():
    """Cycles to the next tab using Ctrl+Tab."""
    try:
        subprocess.run(['xdotool', 'key', 'ctrl+Tab'], check=False)
    except Exception as e:
        logging.error(f"Error cycling tab: {e}")

def refresh_page():
    """Refreshes the current page using Ctrl+R."""
    try:
        # Forces a page reload to prevent stale data
        subprocess.run(['xdotool', 'key', 'ctrl+r'], check=False)
        logging.info("Page refreshed.")
    except Exception as e:
        logging.error(f"Error refreshing page: {e}")

# --- Main Kiosk Loop ---
def main():
    global current_mode, current_url_index, url_refresh_times

    logging.info("--- Kiosk Control Script Started ---")
    
    # Initial delay to let the desktop environment settle
    time.sleep(5)
    
    # Default refresh interval: 1 hour (3600 seconds)
    REFRESH_INTERVAL = 3600 

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
                    time.sleep(60)
                    continue
                
                launch_browser(urls_to_launch)
            
            # --- Tab Switching & Refreshing Logic ---
            if on_urls and len(on_urls) > 0:
                if current_url_index >= len(on_urls):
                    current_url_index = 0 # Loop back to the start
                
                # Get the duration for the current tab
                current_entry = on_urls[current_url_index]
                current_url = current_entry.get('url')
                duration = current_entry.get('duration', 60)
                
                logging.info(f"Displaying tab {current_url_index + 1} ({current_entry.get('notes', 'No notes')}) for {duration}s")

                # 1. Check if refresh is needed (once per hour)
                current_time = time.time()
                last_refreshed = url_refresh_times.get(current_url, 0)
                
                if current_time - last_refreshed > REFRESH_INTERVAL:
                    logging.info(f"Refreshing tab {current_url_index + 1} (Last refreshed > 1h ago)")
                    time.sleep(0.5) # Wait for focus
                    refresh_page()
                    url_refresh_times[current_url] = current_time # Update timestamp
                else:
                    logging.info(f"Skipping refresh for tab {current_url_index + 1} (Refreshed {int(current_time - last_refreshed)}s ago)")

                # 2. Wait for the specified duration
                time.sleep(duration) 
                
                # 3. Switch to the NEXT tab (if more than one)
                if len(on_urls) > 1:
                    cycle_next_tab()
                
                # 4. Increment index for next loop iteration
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

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Script stopped by user (KeyboardInterrupt).")
        kill_browser()
    except Exception as e:
        logging.error(f"--- UNHANDLED EXCEPTION: {e} ---")
        kill_browser()