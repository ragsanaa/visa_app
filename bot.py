import requests
import time
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

UNAVAILABLE_URL = "https://visa-fr-az.capago.eu/en/WebSite_getUnavailableDayList?capago_center_id=capago_baku&formula=standard&visa_file_list=[{%22resource_id%22:%22SSVT%22,%22variation_id%22:%224%22}]&travel_project_relative_url=undefined"
SLOT_URL_TEMPLATE = "https://visa-fr-az.capago.eu/en/WebSite_getAvailableAppointmentSlotList?capago_center_id=capago_baku&formula=standard&day={day}"

# Additional appointment endpoints
APPT_UNAVAILABLE_URL = "https://visa-fr-az.capago.eu/en/appointment/WebSite_getUnavailableDayList?capago_center_id=capago_baku&formula=standard&visa_file_list=&travel_project_relative_url=travel_project_module/004-A17AFBF"
APPT_SLOT_URL_TEMPLATE = "https://visa-fr-az.capago.eu/en/appointment/WebSite_getAvailableAppointmentSlotList?capago_center_id=capago_baku&formula=standard&day={day}"

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def check_slots():
    # Original endpoint: compute available days as all_day_list - unavailable_day_list
    res_main = requests.get(UNAVAILABLE_URL).json()
    unavailable_days_main = set(res_main.get("unavailable_day_list", []))
    available_days_main = [
        d for d in res_main.get("all_day_list", []) if d not in unavailable_days_main
    ]

    # Additional appointment endpoint: directly provides available_day_list
    res_appt = requests.get(APPT_UNAVAILABLE_URL).json()
    available_days_appt = res_appt.get("available_day_list", [])

    # Merge unique days from both sources
    all_available_days = sorted(set(available_days_main) | set(available_days_appt))

    if not all_available_days:
        print("No available days yet.")
        return

    first_day = all_available_days[0]

    # Query both slot endpoints for the chosen day
    slots_url_main = SLOT_URL_TEMPLATE.format(day=first_day)
    slots_res_main = requests.get(slots_url_main).json()
    slots_main = slots_res_main.get("slot_list", []) or slots_res_main.get("available_slot_list", [])

    slots_url_appt = APPT_SLOT_URL_TEMPLATE.format(day=first_day)
    slots_res_appt = requests.get(slots_url_appt).json()
    slots_appt = slots_res_appt.get("available_slot_list", []) or slots_res_appt.get("slot_list", [])

    total_slots = (len(slots_main) if isinstance(slots_main, list) else 0) + (
        len(slots_appt) if isinstance(slots_appt, list) else 0
    )

    if total_slots:
        msg = (
            f"✅ Appointment available!\n"
            f"Day: {first_day}\n"
            f"Slots: {total_slots} (main: {len(slots_main)}, appt: {len(slots_appt)})"
        )
        send_message(msg)
        print(msg)
    else:
        print(f"No slots on {first_day}.")

if __name__ == "__main__":
    while True:
        try:
            check_slots()
        except Exception as e:
            print("Error:", e)
        time.sleep(300)  # run every 5 minutes
