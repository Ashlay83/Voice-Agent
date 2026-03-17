import os
import sys
import time
import requests
from pynput import keyboard
import pyaudio
import wave
import speech_recognition as sr
from faster_whisper import WhisperModel
from contextlib import contextmanager
from src.automation.whatsapp import automate_whatsapp
from src.automation.email import automate_email # <--- NEW IMPORT

# --- CORTEX ADDRESS BOOK ---
# Keys must be completely lowercase to match the voice translation!
CONTACT_BOOK = {
    "deepak": "achuashlay@gmail.com",
    "naveen": "naveensurendran116@gmail.com",
    "hr": "hr@yourcompany.com",
    "professor": "dr.smith@university.edu"
}

# --- CONFIGURATION ---
RASA_SERVER_URL = "http://localhost:5005/webhooks/rest/webhook"
AUDIO_FILENAME = "user_input.wav"
MODEL_PATH = "faster-whisper-malayalam"

# ==========================================
# 0. UTILITIES
# ==========================================
@contextmanager
def silence_c_warnings():
    """Temporarily redirects C-level stderr to /dev/null to hide ALSA/JACK spam."""
    original_stderr = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 2)
    os.close(devnull)
    try:
        yield
    finally:
        os.dup2(original_stderr, 2)
        os.close(original_stderr)

def set_rasa_slot(slot_name, slot_value):
    """Forces exact text directly into Rasa's memory, bypassing NLU."""
    url = "http://localhost:5005/conversations/local_user/tracker/events"
    requests.post(url, json={"event": "slot", "name": slot_name, "value": slot_value})
    print(f"🧠 Memory Updated: '{slot_name}' forcefully set to '{slot_value}'.")

# ==========================================
# 1. THE EARS (Wake Word, Auto-Recording, Translation)
# ==========================================
def wait_for_wake_word():
    recognizer = sr.Recognizer()
    
    # Wrap the microphone initialization in our silencer
    with silence_c_warnings(), sr.Microphone() as source:
        print("\n💤 blue is sleeping. Say 'Hey blue' to wake up...")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        
        while True:
            try:
                audio = recognizer.listen(source, timeout=1, phrase_time_limit=3)
                text = recognizer.recognize_google(audio).lower()
                
                if "blue" in text or "blu" in text:
                    print("\n✨ [AWAKE] blue heard you!")
                    return True 
                    
            except sr.WaitTimeoutError:
                continue 
            except sr.UnknownValueError:
                continue 
            except sr.RequestError:
                print("❌ Wake word service offline. Retrying...")
                time.sleep(2)

def record_command_auto():
    """Starts recording automatically, but waits for Right Shift to stop."""
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    frames = []
    recording = True

    # 1. The keyboard listener to catch the "Full Stop"
    def on_press(key):
        nonlocal recording
        if key == keyboard.Key.shift_r:
            recording = False
            return False # Kills the listener

    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    # 2. Start recording immediately
    with silence_c_warnings():
        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK)

    print("🔴 Speak your command... (Press RIGHT SHIFT to finish)")
    
    # 3. Keep recording until the button is pressed
    while recording:
        data = stream.read(CHUNK, exception_on_overflow=False)
        frames.append(data)

    print("⏹️ [STOPPED] Processing audio...")
    
    # 4. Clean up and save
    stream.stop_stream()
    stream.close()
    p.terminate()

    with wave.open(AUDIO_FILENAME, 'wb') as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b''.join(frames))
        
    return True

   
def translate_audio():
    print("⏳ Translating via Faster-Whisper...")
    # Using your custom trained model on the RTX 3050 Ti
    model = WhisperModel(MODEL_PATH, device="cuda", compute_type="int8_float16")
    segments, _ = model.transcribe(AUDIO_FILENAME, task="translate", language="ml")
    full_text = "".join([segment.text for segment in segments]).strip()
    print(f"🗣️ Translated Text: '{full_text}'")
    return full_text

# ==========================================
# 2. THE HANDS (PyAutoGUI Automation)
# ==========================================



# ==========================================
# 3. THE BRAIN (Rasa Conversational Logic)
# ==========================================
# State tracker to remember what we are modifying
current_modification_target = None

def process_command(text_input):
    global current_modification_target
    if not text_input: 
        return False
    
    print(f"\n🗣️ You: '{text_input}'")
    
    # ==========================================
    # 🚨 THE INTERCEPTOR 🚨
    # ==========================================
    if current_modification_target:
        # 1. Force your perfectly translated text straight into Rasa's memory
        set_rasa_slot(current_modification_target, text_input)
        
        # 2. Tell Rasa to skip guessing and jump straight to the confirmation!
        payload = {"sender": "local_user", "message": "/request_confirmation"}
        
        # 3. Reset the state
        current_modification_target = None 
    else:
        # Normal routing for standard conversation
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
        bot_text = bot_reply.get("text")
        print(f"🤖 Agent: {bot_text}")
        
        # ==========================================
        # 🔀 THE ROUTER (SUCCESS BLOCK)
        # ==========================================
        if "On it! Sending" in bot_text:
            print("⚙️ Processing final command...")
            
            parts = bot_text.split(" message to ")
            if len(parts) > 1:
                # bot_text usually looks like: "On it! Sending a email message to deepak saying 'hello'."
                platform_part = parts[0].lower() 
                
                contact_and_msg = parts[1].split(" saying '")
                contact_name = contact_and_msg[0].lower().strip(" .,!?") # Strips spaces AND Whisper's punctuation!
                message = contact_and_msg[1].replace("'.", "")
                
                # Route to the correct skill!
                if "whatsapp" in platform_part:
                    automate_whatsapp(contact_name, message)
                    
                elif "email" in platform_part or "gmail" in platform_part:
                    # Look up the actual email address in our dictionary!
                    if contact_name in CONTACT_BOOK:
                        actual_email = CONTACT_BOOK[contact_name]
                        automate_email(actual_email, message)
                    else:
                        print(f"❌ ERROR: '{contact_name}' is not in the Cortex Address Book!")
                        print("Skipping email automation.")
                else:
                    print(f"❌ ERROR: Unknown platform requested.")
                
            # Wipe memory after finishing the task
            requests.post(RASA_SERVER_URL, json={"sender": "local_user", "message": "/restart"})
            keep_awake = False 

        # CANCEL
        elif "Message canceled" in bot_text:
            requests.post(RASA_SERVER_URL, json={"sender": "local_user", "message": "/restart"})
            print("🧠 Memory cleared.")
            keep_awake = False 

        # MODIFY CONTACT
        elif "Who should I send it to instead?" in bot_text:
            current_modification_target = "contact"
            keep_awake = True

        # MODIFY MESSAGE
        elif "What should the new message say?" in bot_text:
            current_modification_target = "message_body"
            keep_awake = True

        # ASKING QUESTIONS
        else:
            keep_awake = True 

    return keep_awake

# ==========================================
# 4. MAIN EXECUTION LOOP
# ==========================================
if __name__ == "__main__":
    print("\n🧹 Wiping Rasa's memory for a fresh start...")
    try:
        requests.post(RASA_SERVER_URL, json={"sender": "local_user", "message": "/restart"})
    except Exception:
        pass 

    is_conversing = False
    
    while True:
        try:
            if not is_conversing:
                wait_for_wake_word()
            
            command_captured = record_command_auto()
            
            if command_captured:
                translated_text = translate_audio()
                is_conversing = process_command(translated_text)
            else:
                is_conversing = False 
            
            if not is_conversing:
                print("\n" + "="*50)
                print("🔄 Action complete. Cortex is returning to sleep.")
                print("="*50)
            
        except KeyboardInterrupt:
            print("\n❌ Assistant shut down by user.")
            break