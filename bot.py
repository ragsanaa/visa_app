import requests
import time
import os
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

UNAVAILABLE_URL = "https://visa-fr-az.capago.eu/en/WebSite_getUnavailableDayList?capago_center_id=capago_baku&formula=standard&visa_file_list=[{%22resource_id%22:%22SSVT%22,%22variation_id%22:%224%22}]&travel_project_relative_url=undefined"
SLOT_URL_TEMPLATE = "https://visa-fr-az.capago.eu/en/WebSite_getAvailableAppointmentSlotList?capago_center_id=capago_baku&formula=standard&day={day}"

# Additional appointment endpoints
APPT_UNAVAILABLE_URL = "https://visa-fr-az.capago.eu/en/appointment/WebSite_getUnavailableDayList?capago_center_id=capago_baku&formula=standard&visa_file_list=&travel_project_relative_url=travel_project_module/004-A17AFBF"
APPT_SLOT_URL_TEMPLATE = "https://visa-fr-az.capago.eu/en/appointment/WebSite_getAvailableAppointmentSlotList?capago_center_id=capago_baku&formula=standard&day={day}"

# Common request headers to avoid HTML responses and encourage JSON
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://visa-fr-az.capago.eu/",
}

def fetch_json(url, *, timeout_seconds=20):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout_seconds)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        # Print helpful diagnostics to logs to understand failures
        try:
            snippet = resp.text[:200] if 'resp' in locals() else "<no response>"
            status = resp.status_code if 'resp' in locals() else "<no status>"
        except Exception:
            snippet = "<unavailable>"
            status = "<unavailable>"
        print(f"Fetch JSON error for URL: {url}\nStatus: {status}\nError: {e}\nBody snippet: {snippet}")
        return None

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    # Silence default access logging
    def log_message(self, format, *args):
        return

def start_health_server(port=8000):
    try:
        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"Health server listening on port {port}")
        return server
    except Exception as e:
        print("Failed to start health server:", e)
        return None

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def check_slots():
    # Original endpoint: compute available days as all_day_list - unavailable_day_list
    res_main = fetch_json(UNAVAILABLE_URL)
    if not res_main:
        print("Main days endpoint returned no JSON; skipping this cycle.")
        return
    unavailable_days_main = set(res_main.get("unavailable_day_list", []))
    available_days_main = [
        d for d in res_main.get("all_day_list", []) if d not in unavailable_days_main
    ]

    # Additional appointment endpoint: directly provides available_day_list
    res_appt = fetch_json(APPT_UNAVAILABLE_URL)
    available_days_appt = res_appt.get("available_day_list", []) if isinstance(res_appt, dict) else []

    # Merge unique days from both sources
    all_available_days = sorted(set(available_days_main) | set(available_days_appt))

    if not all_available_days:
        print("No available days yet.")
        return

    # Define cutoff date (inclusive)
    cutoff_date = datetime.fromisoformat("2025-12-10").date()

    def day_to_date(day_str):
        # day strings look like 'YYYY-MM-DDT00:00:00+00:00' or '...Z'
        return datetime.strptime(day_str[:10], "%Y-%m-%d").date()

    days_to_check = [d for d in all_available_days if day_to_date(d) <= cutoff_date]

    if not days_to_check:
        print("No available days before or on 2025-12-10.")
        return

    any_found = False
    for day_str in days_to_check:
        normalized_day = day_str.replace("+00:00", "Z")

        # Query both slot endpoints for this day
        slots_url_main = SLOT_URL_TEMPLATE.format(day=normalized_day)
        slots_res_main = fetch_json(slots_url_main) or {}
        slots_main = slots_res_main.get("slot_list", []) or slots_res_main.get("available_slot_list", [])

        slots_url_appt = APPT_SLOT_URL_TEMPLATE.format(day=normalized_day)
        slots_res_appt = fetch_json(slots_url_appt) or {}
        slots_appt = slots_res_appt.get("available_slot_list", []) or slots_res_appt.get("slot_list", [])

        total_slots = (len(slots_main) if isinstance(slots_main, list) else 0) + (
            len(slots_appt) if isinstance(slots_appt, list) else 0
        )

        if total_slots:
            any_found = True
            msg = (
                f"✅ Appointment available!\n"
                f"Day: {day_str}\n"
                f"Slots: {total_slots} (main: {len(slots_main)}, appt: {len(slots_appt)})"
            )
            send_message(msg)
            print(msg)
        else:
            print(f"No slots on {day_str}.")

    if not any_found:
        print("No slots on any day up to 2025-12-10.")

if __name__ == "__main__":
    # Start a tiny HTTP server on port 8000 so platform TCP/HTTP health checks pass
    start_health_server(port=8000)

    if not BOT_TOKEN or not CHAT_ID:
        print("BOT_TOKEN or CHAT_ID is not set. Exiting.")
        raise SystemExit(1)

    while True:
        try:
            check_slots()
        except Exception as e:
            print("Error:", e)
        time.sleep(180)  # run every 3 minutes
