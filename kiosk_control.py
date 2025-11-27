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

# --- Global ---
browser_process = None
current_url_index = 0
current_mode = None
url_refresh_times = {}
# --- End Global ---

# ======================================================
#  AUTO CLICK SIGN IN - RELATIVE COORDINATES (STRATEGIA 1)
# ======================================================
def auto_click_sign_in():
    """
    Universal popup clicker.
    Clicks the Dynamics popup 'Sign In' using RELATIVE screen coordinates.
    Works on any resolution.
    """
    try:
        # Get display resolution
        geom = subprocess.check_output("xdotool getdisplaygeometry", shell=True).decode().split()
        w, h = int(geom[0]), int(geom[1])

        # Popup is centered.
        # Button is ~60% width, 60% height of the screen (dynamic!).
        x = int(w * 0.60)
        y = int(h * 0.60)

        # Activate Chromium
        subprocess.run("xdotool search --class chromium windowactivate", shell=True)

        # "Wiggle" to force focus (Dynamics modals sometimes block first click)
        subprocess.run(f"xdotool mousemove {w//2} {h//2}", shell=True)
        time.sleep(0.1)
        subprocess.run(f"xdotool mousemove {x} {y}", shell=True)

        # CLICK twice for reliability
        subprocess.run("xdotool click 1", shell=True)
        time.sleep(0.1)
        subprocess.run("xdotool click 1", shell=True)

        logging.info(f"[AUTO-CLICK] Popup click at {x}x{y} (w={w}, h={h})")

        # FALLBACK: try TAB + ENTER too
        subprocess.run("xdotool key Tab", shell=True)
        subprocess.run("xdotool key Tab", shell=True)
        subprocess.run("xdotool key Return", shell=True)

    except Exception as e:
        logging.error(f"auto_click_sign_in(): {e}")


# -------------------------
# CONFIG LOADING
# -------------------------
def load_config():
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"FATAL: Could not load config.json: {e}")
        return None


# -------------------------
# TIME HELPER
# -------------------------
def is_on_hours(start_str, end_str):
    try:
        now = datetime.now().time()
        start = datetime.strptime(start_str, '%H:%M').time()
        end = datetime.strptime(end_str, '%H:%M').time()

        if start <= end:
            return start <= now < end
        else:
            return now >= start or now < end
    except:
        return False


# -------------------------
# BROWSER CONTROL
# -------------------------
def kill_browser():
    global browser_process

    if browser_process and browser_process.poll() is None:
        logging.info(f"Killing Chromium PID {browser_process.pid}")
        try:
            parent = psutil.Process(browser_process.pid)
            children = parent.children(recursive=True)

            for c in children:
                c.terminate()
            parent.terminate()

            gone, alive = psutil.wait_procs([parent] + children, timeout=3)
            for p in alive:
                p.kill()

        except:
            pass

    browser_process = None
    logging.info("Browser terminated.")


def launch_browser(urls):
    global browser_process, url_refresh_times
    kill_browser()

    if not urls:
        logging.error("No URLs to launch.")
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

    logging.info(f"Launching Chromium with {len(urls)} tabs...")

    browser_process = subprocess.Popen(
        command,
        env=os.environ.copy(),
        preexec_fn=os.setsid
    )

    logging.info(f"Chromium PID: {browser_process.pid}")
    time.sleep(15)

    focus_tab(1)
    now = time.time()
    for url in urls:
        url_refresh_times[url] = now


def focus_tab(tab_index):
    try:
        if 1 <= tab_index <= 8:
            subprocess.run(['xdotool', 'key', f'ctrl+{tab_index}'])
    except Exception as e:
        logging.error(e)


def cycle_next_tab():
    try:
        subprocess.run(['xdotool', 'key', 'ctrl+Tab'])
    except:
        pass


def refresh_page():
    try:
        subprocess.run(['xdotool', 'key', 'ctrl+r'])
        logging.info("Page refreshed.")
    except Exception as e:
        logging.error(e)


# -------------------------
# MAIN LOOP
# -------------------------
def main():
    global current_mode, current_url_index, url_refresh_times

    logging.info("==== KIOSK STARTED ====")
    time.sleep(5)

    REFRESH_INTERVAL = 3600  # 1h

    while True:
        # ALWAYS try auto-clicking popup
        auto_click_sign_in()

        config = load_config()
        if not config:
            time.sleep(60)
            continue

        on_urls = config.get("on_urls", [])
        off_url = config.get("off_hours_url")
        on = is_on_hours(config["on_hours_start"], config["on_hours_end"])

        # ---------------------
        # ON HOURS
        # ---------------------
        if on:
            if current_mode != 'ON' or browser_process is None or browser_process.poll() is not None:
                current_mode = 'ON'
                current_url_index = 0
                urls = [u["url"] for u in on_urls if u.get('url')]
                launch_browser(urls)

            if on_urls:
                if current_url_index >= len(on_urls):
                    current_url_index = 0

                entry = on_urls[current_url_index]
                url = entry["url"]
                duration = entry.get("duration", 60)

                logging.info(f"Showing tab {current_url_index+1}: {entry.get('notes','')} ({duration}s)")

                # refresh logic
                now = time.time()
                if now - url_refresh_times.get(url, 0) > REFRESH_INTERVAL:
                    refresh_page()
                    url_refresh_times[url] = now

                time.sleep(duration)

                if len(on_urls) > 1:
                    cycle_next_tab()

                current_url_index += 1

        # ---------------------
        # OFF HOURS
        # ---------------------
        else:
            if current_mode != 'OFF' or browser_process is None or browser_process.poll() is not None:
                current_mode = 'OFF'
                if not off_url:
                    kill_browser()
                else:
                    launch_browser([off_url])

            time.sleep(60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        kill_browser()
    except Exception as e:
        logging.error(f"Unhandled crash: {e}")
        kill_browser()
