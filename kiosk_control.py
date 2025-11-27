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
url_refresh_times = {}
# --- End Global State ---


# -------------------------
# AUTO-CLICK "SIGN IN"
# -------------------------
def auto_click_sign_in():
    """
    Automatically clicks the Dynamics popup: "Sign in".
    It appears every ~24h when Dynamics refreshes token.
    """
    try:
        # Step 1: detect popup window
        result = subprocess.run(
            'xdotool search --name "Sign in"',
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        if result.stdout:
            logging.info("Sign-in popup detected → clicking Enter")
            # Step 2: press Enter (activates the "Sign in" button)
            subprocess.run(
                'xdotool key Return',
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

    except Exception as e:
        logging.error(f"auto_click_sign_in() error: {e}")


# -------------------------
# CONFIGURATION LOADING
# -------------------------
def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        return config
    except Exception as e:
        logging.error(f"FATAL: Could not load config file: {e}")
        return None


# -------------------------
# TIME HELPER
# -------------------------
def is_on_hours(start_str, end_str):
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


# -------------------------
# BROWSER PROCESS CONTROL
# -------------------------
def kill_browser():
    global browser_process

    if browser_process and browser_process.poll() is None:
        logging.info(f"Terminating browser process (PID: {browser_process.pid}).")
        try:
            parent = psutil.Process(browser_process.pid)
            children = parent.children(recursive=True)

            for child in children:
                child.terminate()

            parent.terminate()

            gone, alive = psutil.wait_procs([parent] + children, timeout=3)

            for p in alive:
                logging.warning(f"Force-killing PID {p.pid}")
                p.kill()

        except psutil.NoSuchProcess:
            pass
        except Exception as e:
            logging.error(f"Error during browser termination: {e}")

    browser_process = None


def launch_browser(urls):
    global browser_process, url_refresh_times
    kill_browser()

    if not urls:
        logging.error("No URLs configured.")
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

    logging.info(f"Launching Chromium with {len(urls)} tabs.")

    try:
        browser_process = subprocess.Popen(
            command,
            env=os.environ.copy(),
            preexec_fn=os.setsid
        )
        logging.info(f"Browser PID: {browser_process.pid}")
        time.sleep(15)

        focus_tab(1)
        now = time.time()

        for url in urls:
            url_refresh_times[url] = now

    except Exception as e:
        logging.error(f"Failed to launch Chromium: {e}")


def focus_tab(tab_index):
    try:
        if 1 <= tab_index <= 8:
            subprocess.run(['xdotool', 'key', f'ctrl+{tab_index}'], check=False)
    except Exception as e:
        logging.error(f"Error focusing tab: {e}")


def cycle_next_tab():
    try:
        subprocess.run(['xdotool', 'key', 'ctrl+Tab'], check=False)
    except Exception as e:
        logging.error(f"Error cycling tab: {e}")


def refresh_page():
    try:
        subprocess.run(['xdotool', 'key', 'ctrl+r'], check=False)
        logging.info("Page refreshed.")
    except Exception as e:
        logging.error(f"Error refreshing page: {e}")


# -------------------------
# MAIN LOOP
# -------------------------
def main():
    global current_mode, current_url_index, url_refresh_times

    logging.info("--- Kiosk Control Script Started ---")
    time.sleep(5)

    REFRESH_INTERVAL = 3600  # refresh each tab every 1 hour

    while True:

        # 🔥 ALWAYS check and auto-click popup
        auto_click_sign_in()

        config = load_config()
        if not config:
            logging.error("Retrying config load in 60s...")
            time.sleep(60)
            continue

        on_urls = config.get('on_urls', [])
        off_url = config.get('off_hours_url')
        on = is_on_hours(config.get('on_hours_start'), config.get('on_hours_end'))

        # ---------------------
        # ON HOURS
        # ---------------------
        if on:

            if current_mode != 'ON' or browser_process is None or browser_process.poll() is not None:
                logging.info("Entering ON mode")
                current_mode = 'ON'
                current_url_index = 0

                urls_to_launch = [entry['url'] for entry in on_urls if entry.get('url')]

                if not urls_to_launch:
                    logging.warning("ON mode active but no URLs. Waiting.")
                    time.sleep(60)
                    continue

                launch_browser(urls_to_launch)

            if on_urls:
                if current_url_index >= len(on_urls):
                    current_url_index = 0

                entry = on_urls[current_url_index]
                url = entry.get('url')
                duration = entry.get('duration', 60)

                logging.info(f"Tab {current_url_index + 1} => {entry.get('notes', 'No notes')} for {duration}s")

                now = time.time()
                last_refresh = url_refresh_times.get(url, 0)

                if now - last_refresh > REFRESH_INTERVAL:
                    logging.info(f"Refreshing tab {current_url_index + 1}")
                    refresh_page()
                    url_refresh_times[url] = now

                time.sleep(duration)

                if len(on_urls) > 1:
                    cycle_next_tab()

                current_url_index += 1

            else:
                time.sleep(60)

        # ---------------------
        # OFF HOURS
        # ---------------------
        else:
            if current_mode != 'OFF' or browser_process is None or browser_process.poll() is not None:
                logging.info("Entering OFF mode")
                current_mode = 'OFF'

                if not off_url:
                    logging.warning("No off-hours URL → killing browser")
                    kill_browser()
                else:
                    launch_browser([off_url])

            time.sleep(60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Script stopped manually.")
        kill_browser()
    except Exception as e:
        logging.error(f"UNHANDLED EXCEPTION: {e}")
        kill_browser()
