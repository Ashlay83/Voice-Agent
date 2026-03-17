import pyaudio
import wave
from faster_whisper import WhisperModel
from pynput import keyboard
import time
import requests
from src.automation.whatsapp import automate_whatsapp


# --- CONFIGURATION ---
RASA_SERVER_URL = "http://localhost:5005/webhooks/rest/webhook"
AUDIO_FILENAME = "user_input.wav"
TOGGLE_KEY = keyboard.Key.shift_r  # Right Shift for Push-to-Talk

# --- AUDIO SETTINGS ---
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100  # Change to 48000 if your mic gave ALSA errors before
CHUNK = 1024

# Global state variables
is_recording = False
keep_listening = True
frames = []

# ==========================================
# 1. THE EARS (Microphone & Translation)
# ==========================================
def on_press(key):
    global is_recording, keep_listening
    if key == TOGGLE_KEY:
        if not is_recording:
            is_recording = True
            print("\n🔴 [RECORDING] Speak your command... (Press Right Shift to stop)")
        else:
            is_recording = False
            keep_listening = False
            print("⏹️ [STOPPED] Processing audio...")
            return False

def record_audio():
    global is_recording, keep_listening, frames
    keep_listening = True
    frames = []
    
    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                    input=True, frames_per_buffer=CHUNK)
    
    print(f"\n👉 Press RIGHT SHIFT to start listening...")
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    
    while keep_listening:
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
            if is_recording:
                frames.append(data)
        except IOError:
            pass
        time.sleep(0.001)
            
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    wf = wave.open(AUDIO_FILENAME, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()

def translate_audio():
    print("⏳ Translating via Faster-Whisper...")
    model = WhisperModel("faster-whisper-malayalam", device="cuda", compute_type="int8_float16")
    segments, _ = model.transcribe(
        AUDIO_FILENAME,
        task="translate",
        language="ml",
        initial_prompt="Send a message to a person on an app. For example: Send a WhatsApp message to Deepak saying hi."
    )
    full_text = "".join([segment.text for segment in segments]).strip()
    print(f"🗣️ Translated Text: '{full_text}'")
    return full_text


def process_command(text_input):
    if not text_input: return
    
    print(f"\n🗣️ You: '{text_input}'")
    
    # Notice the payload is different now! We are identifying the user so Rasa remembers them.
    payload = {
        "sender": "local_user", 
        "message": text_input
    }
    
    try:
        response = requests.post(RASA_SERVER_URL, json=payload)
        response.raise_for_status()
        bot_responses = response.json()
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Rasa server is not running!")
        return

    
    
    # Helper API call to erase a specific slot from Rasa's memory
    def clear_rasa_slot(slot_name):
        url = "http://localhost:5005/conversations/local_user/tracker/events"
        requests.post(url, json={"event": "slot", "name": slot_name, "value": None})
        print(f"🧠 Memory Erased: The '{slot_name}' slot has been cleared.")

    # Loop through whatever Rasa decides to say back
    for bot_reply in bot_responses:
        bot_text = bot_reply.get("text")
        print(f"🤖 Agent: {bot_text}")
        
        # 1. SUCCESS: Trigger PyAutoGUI
        if "On it! Sending" in bot_text:
            print("⚙️ Triggering PyAutoGUI Automation...")
            parts = bot_text.split(" message to ")
            if len(parts) > 1:
                contact_and_msg = parts[1].split(" saying '")
                contact = contact_and_msg[0]
                message = contact_and_msg[1].replace("'.", "")
                
                automate_whatsapp(contact, message)
                
            # Wipe all memory after a successful send
            requests.post(RASA_SERVER_URL, json={"sender": "local_user", "message": "/restart"})

        # 2. MODIFY CONTACT: Clear just the contact slot
        elif "Who should I send it to instead?" in bot_text:
            clear_rasa_slot("contact")

        # 3. MODIFY MESSAGE: Clear just the message slot
        elif "What should the new message say?" in bot_text:
            clear_rasa_slot("message_body")

        # 4. CANCEL EVERYTHING: Wipe all memory
        elif "Message canceled. Let's start over" in bot_text:
            requests.post(RASA_SERVER_URL, json={"sender": "local_user", "message": "/restart"})
            print("🧠 Full memory cleared. Ready for a new command.")
# ==========================================
# MAIN EXECUTION LOOP
# ==========================================
if __name__ == "__main__":
    while True:
        try:
            # 1. Listen
            record_audio()
            # 2. Translate
            translated_text = translate_audio()
            # 3. Execute
            process_command(translated_text)
            
            print("\n" + "="*50)
            print("🔄 Loop complete. Ready for next command.")
            print("="*50)
            
        except KeyboardInterrupt:
            print("\n❌ Assistant shut down by user.")
            break