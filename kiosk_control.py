import subprocess
import time
import json
import logging
from datetime import datetime
import os
import psutil

# --- Konfiguracja ---
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')
LOG_FILE = os.path.join(os.path.dirname(__file__), 'kiosk.log')
# --- Koniec konfiguracji ---

# --- Ustawienia logowania ---
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
# --- Koniec ustawień logowania ---

# --- Stan globalny ---
browser_process = None
current_url_index = 0
current_mode = None  # 'ON' lub 'OFF'
url_refresh_times = {} # Przechowuje znacznik czasu ostatniego odświeżenia dla każdego adresu URL
tabs_initialized = set() # Śledzi, które karty miały wykonane wstępne czyszczenie popupów
# --- Koniec stanu globalnego ---

def load_config():
    """Wczytuje konfigurację z pliku config.json."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        logging.info("Konfiguracja wczytana pomyślnie.")
        return config
    except Exception as e:
        logging.error(f"FATALNIE: Nie można wczytać pliku konfiguracyjnego: {e}")
        return None

def is_on_hours(start_str, end_str):
    """Sprawdza, czy bieżący czas mieści się w godzinach 'włączenia'."""
    try:
        now = datetime.now().time()
        start_time = datetime.strptime(start_str, '%H:%M').time()
        end_time = datetime.strptime(end_str, '%H:%M').time()

        if start_time <= end_time:
            return start_time <= now < end_time
        else:
            return now >= start_time or now < end_time
    except Exception as e:
        logging.error(f"Błąd podczas sprawdzania czasu: {e}")
        return False

def kill_browser():
    """Znajduje i kończy wszelkie istniejące procesy Chromium."""
    global browser_process
    
    if browser_process and browser_process.poll() is None:
        logging.info(f"Kończenie istniejącego procesu przeglądarki (PID: {browser_process.pid}).")
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
            logging.info(f"Proces {browser_process.pid} już nie istnieje.")
        except Exception as e:
            logging.error(f"Błąd podczas kończenia procesu: {e}")
    
    browser_process = None
    logging.info("Proces przeglądarki zakończony.")

def close_popup():
    """Symuluje naciśnięcie ESC, aby zamknąć irytujące popupy, takie jak logowanie PowerBI."""
    try:
        logging.info("Wysyłanie ESC, aby zamknąć potencjalne popupy...")
        subprocess.run(
            ['xdotool', 'search', '--onlyvisible', '--class', 'chromium', 'windowactivate', '--sync', 'key', 'Escape', 'sleep', '0.5', 'key', 'Escape'],
            check=False
        )
    except Exception as e:
        logging.error(f"Błąd podczas wysyłania ESC: {e}")

def launch_browser(urls):
    """Uruchamia Chromium z podanymi adresami URL."""
    global browser_process, url_refresh_times, tabs_initialized
    kill_browser()

    if not urls:
        logging.error("Nie podano adresów URL do uruchomienia.")
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

    logging.info(f"Uruchamianie nowej sesji przeglądarki z {len(urls)} kartami.")
    try:
        browser_process = subprocess.Popen(
            command, 
            env=os.environ.copy(),
            preexec_fn=os.setsid
        )
        logging.info(f"Przeglądarka uruchomiona z PID: {browser_process.pid}")
        
        time.sleep(15) 
        
        # Resetowanie stanu
        url_refresh_times = {}
        tabs_initialized = set() # Resetowanie śledzenia inicjalizacji
        
        # Obsługa pierwszego popupu w logice pętli głównej
        
    except Exception as e:
        logging.error(f"Nie udało się uruchomić przeglądarki: {e}")
        browser_process = None

def focus_tab(tab_index):
    """Aktywuje określoną kartę."""
    try:
        if tab_index <= 8:
            key = f"ctrl+{tab_index}"
        else:
            return
        subprocess.run(['xdotool', 'key', key], check=False)
    except Exception as e:
        logging.error(f"Błąd podczas aktywowania karty {tab_index}: {e}")

def cycle_next_tab():
    """Przełącza na następną kartę."""
    try:
        subprocess.run(['xdotool', 'key', 'ctrl+Tab'], check=False)
    except Exception as e:
        logging.error(f"Błąd podczas przełączania karty: {e}")

def refresh_page():
    """Odświeża bieżącą stronę."""
    try:
        subprocess.run(['xdotool', 'key', 'ctrl+r'], check=False)
        logging.info("Strona odświeżona.")
    except Exception as e:
        logging.error(f"Błąd podczas odświeżania strony: {e}")

# --- Główna pętla kiosku ---
def main():
    global current_mode, current_url_index, url_refresh_times, tabs_initialized

    logging.info("--- Skrypt sterujący kioskiem uruchomiony ---")
    time.sleep(5)
    
    # Interwał odświeżania: 1 godzina (3600 sekund)
    REFRESH_INTERVAL = 3600 

    while True:
        config = load_config()
        if not config:
            logging.error("Ponawianie próby wczytania konfiguracji za 60s...")
            time.sleep(60)
            continue
        
        on_urls = config.get('on_urls', [])
        off_url = config.get('off_hours_url')
        
        on = is_on_hours(config.get('on_hours_start'), config.get('on_hours_end'))
        
        if on:
            # --- GODZINY WŁĄCZENIA ---
            if current_mode != 'ON' or browser_process is None or browser_process.poll() is not None:
                logging.info("Wchodzenie w tryb 'Godziny włączenia'.")
                current_mode = 'ON'
                current_url_index = 0
                
                urls_to_launch = [entry['url'] for entry in on_urls if entry.get('url')]
                if not urls_to_launch:
                    logging.warning("Tryb 'Godziny włączenia' aktywny, ale nie skonfigurowano adresów URL.")
                    time.sleep(60)
                    continue
                
                launch_browser(urls_to_launch)
            
            # --- Przełączanie kart i odświeżanie ---
            if on_urls and len(on_urls) > 0:
                if current_url_index >= len(on_urls):
                    current_url_index = 0
                
                current_entry = on_urls[current_url_index]
                current_url = current_entry.get('url')
                duration = current_entry.get('duration', 60)
                
                logging.info(f"Wyświetlanie karty {current_url_index + 1} ({current_entry.get('notes', 'Brak notatek')}) przez {duration}s")

                # Zawsze wykonuj close_popup po przełączeniu na kartę
                # Daje to pewność, że jeśli popup pojawił się w tle, zostanie zamknięty teraz
                time.sleep(2) # Poczekaj chwilę po przełączeniu, aby karta stała się aktywna
                close_popup()

                # Sprawdź logikę odświeżania (uruchom przy starcie LUB co godzinę)
                current_time = time.time()
                last_refreshed = url_refresh_times.get(current_url, 0)
                needs_refresh = (current_time - last_refreshed > REFRESH_INTERVAL)
                
                if needs_refresh:
                    logging.info(f"Odświeżanie karty {current_url_index + 1}...")
                    
                    # Odśwież, aby pobrać najnowsze dane
                    refresh_page()
                    url_refresh_times[current_url] = current_time
                    
                    # Po odświeżeniu również spróbuj zamknąć popup
                    time.sleep(5) 
                    close_popup()
                else:
                    logging.info(f"Pominięcie odświeżania (Odświeżono {int(current_time - last_refreshed)}s temu)")
                
                # 2. Czekaj przez określony czas
                # (Odejmujemy czas poświęcony na obsługę popupów, aby zachować płynność, ale tutaj po prostu czekamy)
                time.sleep(duration) 
                
                # 3. Przełącz kartę (jeśli jest więcej niż jedna)
                if len(on_urls) > 1:
                    cycle_next_tab()
                
                current_url_index += 1
            else:
                time.sleep(60)

        else:
            # --- GODZINY WYŁĄCZENIA ---
            if current_mode != 'OFF' or browser_process is None or browser_process.poll() is not None:
                logging.info("Wchodzenie w tryb 'Godziny wyłączenia'.")
                current_mode = 'OFF'
                if not off_url:
                    logging.warning("Nie skonfigurowano adresu URL dla godzin wyłączenia.")
                    kill_browser()
                else:
                    launch_browser([off_url])
            
            time.sleep(60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logging.info("Skrypt zatrzymany przez użytkownika.")
        kill_browser()
    except Exception as e:
        logging.error(f"--- NIEODŁUŻONY WYJĄTEK: {e} ---")
        kill_browser()