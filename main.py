import pyaudio
import wave
from faster_whisper import WhisperModel
from pynput import keyboard
import time
import requests
import pyautogui

# --- CONFIGURATION ---
RASA_SERVER_URL = "http://localhost:5005/model/parse"
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
    model = WhisperModel("medium", device="cuda", compute_type="int8_float16")
    segments, _ = model.transcribe(
        AUDIO_FILENAME,
        task="translate",
        language="ml",
        initial_prompt="Send a message to a person on an app. For example: Send a WhatsApp message to Deepak saying hi."
    )
    full_text = "".join([segment.text for segment in segments]).strip()
    print(f"🗣️ Translated Text: '{full_text}'")
    return full_text


# ==========================================
# 2. THE HANDS (PyAutoGUI Automation)
# ==========================================
def wait_and_click(image_path, timeout=20, click=True):
    print(f"👀 Scanning for {image_path}...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            location = pyautogui.locateCenterOnScreen(image_path, confidence=0.8)
            if location:
                print(f"🎯 Found {image_path}!")
                if click:
                    pyautogui.moveTo(location.x, location.y, duration=0.3)
                    pyautogui.click()
                return True
        except pyautogui.ImageNotFoundException:
            pass
        time.sleep(0.5)
        
    print(f"❌ TIMEOUT: Could not find {image_path}.")
    return False

def automate_whatsapp(contact, message):
    print("\n🚀 STARTING VISUAL AUTOMATION...")
    
    # 1. Click Browser Icon on Taskbar
    if not wait_and_click("assets/browser_icon.png"): return
    time.sleep(1) 
    
    # 2. Open New Tab (Using Hotkey is much more reliable than an image)
    print("⌨️ Pressing Ctrl+T for New Tab...")
    pyautogui.hotkey('ctrl', 't')
    time.sleep(1)
    
    # 3. Click the WhatsApp Bookmark
    if not wait_and_click("assets/whatsapp_bookmark.png"): return
    
    # 4. Wait for WhatsApp to load, click Search Bar
    # 4. Wait for WhatsApp to load, click Search Bar
    print("⏳ Waiting for WhatsApp Web to load...")
    if not wait_and_click("assets/search_bar.png", timeout=30): return
    
    # Type contact and hit enter
    pyautogui.write(contact, interval=0.1)
    time.sleep(1.5) # Wait for search to populate
    pyautogui.press("enter")
    
    # 5. Type the message (WhatsApp auto-focuses the cursor here!)
    print("⌨️ Typing the message...")
    time.sleep(1) # Give the chat window 1 second to fully slide open
    pyautogui.write(message, interval=0.05)
    
    # 6. Press Enter to Send (No need for the send button image!)
    time.sleep(0.5)
    pyautogui.press("enter")
    
    print("✅ MESSAGE SENT SUCCESSFULLY!")


# ==========================================
# 3. THE BRAIN (Rasa Processing & Logic)
# ==========================================
def process_command(text_input):
    if not text_input: return
    
    print(f"\n🌐 Sending to Rasa: '{text_input}'")
    try:
        response = requests.post(RASA_SERVER_URL, json={"text": text_input})
        response.raise_for_status()
        nlu_data = response.json()
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Rasa server is not running!")
        return

    intent = nlu_data['intent']['name']
    entities = {e['entity']: e['value'] for e in nlu_data['entities']}
    
    if intent == "send_message":
        platform = entities.get("platform", "").lower()
        contact = entities.get("contact")
        message_body = entities.get("message_body")
        
        print(f"🧠 Rasa Parsed -> Platform: {platform} | Contact: {contact} | Message: {message_body}")
        
        if platform == "whatsapp" and contact and message_body:
            automate_whatsapp(contact, message_body)
        else:
            print("⚠️ Missing data! Rasa didn't catch platform, contact, or message.")
    else:
        print(f"🤷 Unhandled Intent: {intent}")

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