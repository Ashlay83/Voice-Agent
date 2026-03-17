import os
import time
import requests
from src.automation.whatsapp import automate_whatsapp
from src.automation.email import automate_email

# ── NEW: import everything from the improved audio pipeline ──────────────────
from audio_pipeline import wait_for_wake_word
from audio_pipeline import record_command_auto
from audio_pipeline import translate_audio
from audio_pipeline import set_rasa_slot
from audio_pipeline import  silence_c_warnings
from audio_pipeline import  LANGUAGE

# ─────────────────────────────────────────────────────────────────────────────

# --- CORTEX ADDRESS BOOK ---
CONTACT_BOOK = {
    "deepak":    "achuashlay@gmail.com",
    "naveen":    "naveensurendran116@gmail.com",
    "hr":        "hr@yourcompany.com",
    "professor": "dr.smith@university.edu",
}

# --- CONFIGURATION ---
RASA_SERVER_URL = "http://localhost:5005/webhooks/rest/webhook"

# ==========================================
# 3. THE BRAIN (Rasa Conversational Logic)
# ==========================================
current_modification_target = None

def process_command(text_input):
    global current_modification_target
    if not text_input:
        return False

    print(f"\n🗣️  You: '{text_input}'")

    if current_modification_target:
        set_rasa_slot(current_modification_target, text_input)
        payload = {"sender": "local_user", "message": "/request_confirmation"}
        current_modification_target = None
    else:
        payload = {"sender": "local_user", "message": text_input}

    try:
        response = requests.post(RASA_SERVER_URL, json=payload)
        response.raise_for_status()
        bot_responses = response.json()
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Rasa server is not running!")
        return False

    keep_awake = False

    for bot_reply in bot_responses:
        bot_text = bot_reply.get("text", "")
        print(f"🤖 Agent: {bot_text}")

        if "On it! Sending" in bot_text:
            print("⚙️  Processing final command…")
            parts = bot_text.split(" message to ")
            if len(parts) > 1:
                platform_part      = parts[0].lower()
                contact_and_msg    = parts[1].split(" saying '")
                contact_name       = contact_and_msg[0].lower().strip()
                message            = contact_and_msg[1].replace("'.", "")

                if "whatsapp" in platform_part:
                    automate_whatsapp(contact_name, message)
                elif "email" in platform_part or "gmail" in platform_part:
                    if contact_name in CONTACT_BOOK:
                        automate_email(CONTACT_BOOK[contact_name], message)
                    else:
                        print(f"❌ '{contact_name}' not in Address Book.")
                else:
                    print("❌ Unknown platform.")

            requests.post(RASA_SERVER_URL, json={"sender": "local_user", "message": "/restart"})
            keep_awake = False

        elif "Message canceled" in bot_text:
            requests.post(RASA_SERVER_URL, json={"sender": "local_user", "message": "/restart"})
            print("🧠 Memory cleared.")
            keep_awake = False

        elif "Who should I send it to instead?" in bot_text:
            current_modification_target = "contact"
            keep_awake = True

        elif "What should the new message say?" in bot_text:
            current_modification_target = "message_body"
            keep_awake = True

        else:
            keep_awake = True

    return keep_awake


# ==========================================
# 4. MAIN EXECUTION LOOP
# ==========================================
if __name__ == "__main__":
    print(f"\n🌐 Active language: {LANGUAGE.upper()} → English")
    print("🧹 Wiping Rasa memory for a fresh start…")
    try:
        requests.post(RASA_SERVER_URL, json={"sender": "local_user", "message": "/restart"})
    except Exception:
        pass

    is_conversing = False

    while True:
        try:
            if not is_conversing:
                wait_for_wake_word()

            # record_command_auto() now returns False if VAD finds no speech
            command_captured = record_command_auto()

            if command_captured:
                translated_text = translate_audio()   # uses LANGUAGE constant
                is_conversing   = process_command(translated_text)
            else:
                print("⚠️  No usable speech found — returning to listen mode.")
                is_conversing = False

            if not is_conversing:
                print("\n" + "=" * 50)
                print("🔄 Action complete. Cortex is returning to sleep.")
                print("=" * 50)

        except KeyboardInterrupt:
            print("\n❌ Assistant shut down by user.")
            break