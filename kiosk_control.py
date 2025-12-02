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
url_refresh_times = {} # Stores timestamp of last refresh for each URL
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
            return start_time <= now < end_time
        else:
            return now >= start_time or now < end_time
    except Exception as e:
        logging.error(f"Error in time check: {e}")
        return False

def kill_browser():
    """Finds and terminates any existing Chromium process."""
    global browser_process
    
    if browser_process and browser_process.poll() is None:
        logging.info(f"Terminating existing browser process (PID: {browser_process.pid}).")
        try:
            parent = psutil.Process(browser_process.pid)
            children = parent.children(recursive=True)
            for child in children:
                child.terminate()
            parent.terminate()
            gone, alive = psutil.wait_procs([parent] + children, timeout=3)
            for p in alive:
                p.kill()
        except psutil.NoSuchProcess:
            logging.info(f"Process {browser_process.pid} already gone.")
        except Exception as e:
            logging.error(f"Error during process termination: {e}")
    
    browser_process = None
    logging.info("Browser process terminated.")

def close_popup():
    """Simulates pressing ESC to close annoying popups like PowerBI login."""
    try:
        logging.info("Sending ESC to close potential popups...")
        subprocess.run(
            ['xdotool', 'search', '--onlyvisible', '--class', 'chromium', 'windowactivate', '--sync', 'key', 'Escape', 'sleep', '0.5', 'key', 'Escape'],
            check=False
        )
    except Exception as e:
        logging.error(f"Error sending ESC: {e}")

def launch_browser(urls):
    """Launches Chromium with the specified URLs."""
    global browser_process, url_refresh_times
    kill_browser()

    if not urls:
        logging.error("No URLs provided to launch.")
        return

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
        '--window-size=1920,1080',
        '--start-fullscreen',
        f'--user-data-dir={user_data_dir}' 
    ] + urls

    logging.info(f"Launching new browser session with {len(urls)} tabs.")
    try:
        browser_process = subprocess.Popen(
            command, 
            env=os.environ.copy(),
            preexec_fn=os.setsid
        )
        logging.info(f"Browser launched with PID: {browser_process.pid}")
        
        time.sleep(15) 
        
        # Reset refresh times to 0 so the main loop triggers a refresh/ESC immediately for ALL tabs
        url_refresh_times = {}
        
        # We handle the first tab popup in the main loop logic now
        
    except Exception as e:
        logging.error(f"Failed to launch browser: {e}")
        browser_process = None

def focus_tab(tab_index):
    """Focuses a specific tab."""
    try:
        if tab_index <= 8:
            key = f"ctrl+{tab_index}"
        else:
            return
        subprocess.run(['xdotool', 'key', key], check=False)
    except Exception as e:
        logging.error(f"Error focusing tab {tab_index}: {e}")

def cycle_next_tab():
    """Cycles to the next tab."""
    try:
        subprocess.run(['xdotool', 'key', 'ctrl+Tab'], check=False)
    except Exception as e:
        logging.error(f"Error cycling tab: {e}")

def refresh_page():
    """Refreshes the current page."""
    try:
        subprocess.run(['xdotool', 'key', 'ctrl+r'], check=False)
        logging.info("Page refreshed.")
    except Exception as e:
        logging.error(f"Error refreshing page: {e}")

# --- Main Kiosk Loop ---
def main():
    global current_mode, current_url_index, url_refresh_times

    logging.info("--- Kiosk Control Script Started ---")
    time.sleep(5)
    
    # Refresh interval: 1 hour (3600 seconds)
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
                    logging.warning("'On Hours' mode active, but no URLs configured.")
                    time.sleep(60)
                    continue
                
                launch_browser(urls_to_launch)
            
            # --- Tab Switching & Refreshing ---
            if on_urls and len(on_urls) > 0:
                if current_url_index >= len(on_urls):
                    current_url_index = 0
                
                current_entry = on_urls[current_url_index]
                current_url = current_entry.get('url')
                duration = current_entry.get('duration', 60)
                
                logging.info(f"Displaying tab {current_url_index + 1} ({current_entry.get('notes', 'No notes')}) for {duration}s")

                # If we just launched, we need to make sure we are focused on the correct tab
                # because launch_browser no longer forces tab 1 focus immediately.
                # However, browser starts on tab 1.
                # If we cycle, we are fine.
                # To be robust for the "first run" or "refresh" logic:
                
                # Check refresh logic (Run at start OR every hour)
                current_time = time.time()
                last_refreshed = url_refresh_times.get(current_url, 0)
                
                if current_time - last_refreshed > REFRESH_INTERVAL:
                    logging.info(f"Performing maintenance on tab {current_url_index + 1} (Refresh + Close Popup)")
                    
                    # Ensure window focus
                    time.sleep(0.5)
                    
                    # We might need to explicitly focus the tab if it's not the first one or cycling didn't align perfectly yet (rare but possible on start)
                    # But assuming cycle_next_tab works, we are on the right tab.
                    
                    # Refresh to get latest data
                    refresh_page()
                    
                    # Wait for load, then kill popup
                    # This runs on the FIRST visit and every hour after
                    time.sleep(5) # Increased wait time for slow PowerBI load
                    close_popup()
                    
                    # Update timestamp
                    url_refresh_times[current_url] = current_time
                else:
                    # Even if not refreshing, try closing popup just in case it appeared late
                    # This is lightweight enough to do every time
                    time.sleep(2)
                    close_popup()
                    logging.info(f"Skipping refresh (Refreshed {int(current_time - last_refreshed)}s ago)")
                
                # 2. Wait for the specified duration
                # Deduct time spent on maintenance logic to keep overall timing roughly accurate
                # or just wait full duration. Waiting full duration is safer.
                time.sleep(duration) 
                
                # 3. Switch tab (if more than one)
                if len(on_urls) > 1:
                    cycle_next_tab()
                
                current_url_index += 1
            else:
                time.sleep(60)

        else:
            # --- OFF HOURS ---
            if current_mode != 'OFF' or browser_process is None or browser_process.poll() is not None:
                logging.info("Entering 'Off Hours' mode.")
                current_mode = 'OFF'
                if not off_url:
                    logging.warning("No off-hours URL configured.")
                    kill_browser()
                else:
                    launch_browser([off_url])
            
            time.sleep(60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Script stopped by user.")
        kill_browser()
    except Exception as e:
        logging.error(f"--- UNHANDLED EXCEPTION: {e} ---")
        kill_browser()