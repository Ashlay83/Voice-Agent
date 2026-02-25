import pyaudio
import wave
from faster_whisper import WhisperModel  # <--- NEW
from pynput import keyboard
import time
import requests  # <--- NEW: To talk to Rasa
import json      # <--- NEW: To format the output nicely

# --- CONFIGURATION ---
AUDIO_FILENAME = "user_input.wav"
TOGGLE_KEY = keyboard.Key.shift_r  # Right Shift key

# Audio settings
FORMAT = pyaudio.paInt16
CHANNELS = 1
# Note: If 44100 still gives an error, your ASUS TUF mic might require 48000.
RATE = 44100 
CHUNK = 1024

# Global state variables
is_recording = False
keep_listening = True
frames = []

def on_press(key):
    global is_recording, keep_listening
    
    if key == TOGGLE_KEY:
        if not is_recording:
            # START SAVING DATA
            is_recording = True
            print("\n🔴 [RECORDING STARTED] Speak Malayalam now... (Press Right Shift to stop)")
        else:
            # STOP SAVING DATA
            is_recording = False
            keep_listening = False # Stop the script
            print("⏹️ [RECORDING STOPPED] Saving audio...")
            return False # Exits the keyboard listener

def record_audio():
    global is_recording, keep_listening, frames
    
    p = pyaudio.PyAudio()
    
    # FIX: Open the stream ONCE before the loop starts to keep ALSA happy.
    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK)
    
    print(f"👉 Press the RIGHT SHIFT key to start recording...")
    
    # Start the keyboard listener
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    
    # Safely read from the mic stream continuously
    while keep_listening:
        try:
            # We read the data no matter what to keep the buffer from overflowing
            data = stream.read(CHUNK, exception_on_overflow=False)
            
            # But we ONLY save it if the user has pressed Right Shift
            if is_recording:
                frames.append(data)
        except IOError as e:
            pass # Ignore random Linux ALSA buffer warnings
            
        # A tiny sleep keeps your CPU from maxing out at 100%
        time.sleep(0.001) 
            
    # Clean up safely
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    # Save the file
    wf = wave.open(AUDIO_FILENAME, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(p.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()
    print(f"💾 Audio saved as {AUDIO_FILENAME}")

def translate_audio():
    print("⏳ Loading Faster-Whisper model (medium)...")
    
    # device="cuda" uses your GPU
    # compute_type="int8_float16" compresses it to fit in your 4GB VRAM
    model = WhisperModel("medium", device="cuda", compute_type="int8_float16")
    
    print("🧠 Translating Malayalam to English...")
    
    # Transcribe and translate
 
    segments, info = model.transcribe(
        AUDIO_FILENAME,
        task="translate",
        language="ml",
        # The prompt forces Whisper to frame the translation as a command
        initial_prompt="Send a message to a person on an app. For example: Send a WhatsApp message to Deepak saying hi."
    )
    
    # Faster-whisper returns an iterator, so we join the segments
    full_text = "".join([segment.text for segment in segments])
    
    print("\n" + "="*40)
    print(f"🗣️ YOU SAID (Translated): '{full_text.strip()}'")
    print("="*40 + "\n")
    
    return full_text.strip()

RASA_SERVER_URL = "http://localhost:5005/model/parse"

def get_intent_from_rasa(text_input):
    print(f"\n🌐 Sending to Rasa Brain: '{text_input}'...")
    payload = {"text": text_input}
    
    try:
        response = requests.post(RASA_SERVER_URL, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        print("❌ ERROR: Rasa server is not running!")
        print("   Make sure to run 'rasa run --enable-api' in your src/nlu folder.")
        return None

if __name__ == "__main__":
    try:
        record_audio()
        translated_text = translate_audio()
        
        # --- NEW: Send to Rasa and print JSON ---
        if translated_text:
            rasa_json = get_intent_from_rasa(translated_text)
            
            if rasa_json:
                print("\n" + "="*40)
                print("🧠 RASA BRAIN OUTPUT (JSON):")
                print(json.dumps(rasa_json, indent=2))
                print("="*40 + "\n")
                
    except KeyboardInterrupt:
        print("\n❌ Process canceled by user.")