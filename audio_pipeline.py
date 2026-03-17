
import os
import sys
import time
import wave
import struct
import threading
import numpy as np
import requests
import pyaudio
import webrtcvad
import noisereduce as nr
import speech_recognition as sr
from contextlib import contextmanager
from pynput import keyboard
from scipy.signal import butter, sosfilt
from faster_whisper import WhisperModel


# ══════════════════════════════════════════════════════════════
#  CONFIGURATION  — change these to suit your setup
# ══════════════════════════════════════════════════════════════

# "ml" = Malayalam,  "hi" = Hindi
#  Add more ISO-639 codes as needed (e.g. "ta" Tamil, "te" Telugu)
LANGUAGE            = "ml"

MODEL_PATH          = "faster-whisper-malayalam"   # your fine-tuned model
RASA_SERVER_URL     = "http://localhost:5005/webhooks/rest/webhook"
AUDIO_FILENAME      = "user_input.wav"
CLEANED_FILENAME    = "user_input_clean.wav"

# Recording
SAMPLE_RATE         = 16_000          # Hz  – Whisper's native rate
CHUNK_SIZE          = 480             # 30 ms frames required by webrtcvad
FORMAT              = pyaudio.paInt16
CHANNELS            = 1

# Noise reduction
NOISE_PROFILE_SEC   = 0.50            # seconds of leading silence to profile
NOISE_PROP_DECREASE = 0.85            # 0-1 – how aggressively to reduce noise

# Bandpass filter  (speech range)
BP_LOW_HZ           = 80
BP_HIGH_HZ          = 7_800
BP_ORDER            = 4

# VAD
VAD_MODE            = 3               # 0 (lenient) → 3 (aggressive)
VAD_MIN_SPEECH_SEC  = 0.30            # reject clips shorter than this

# Whisper decoding
BEAM_SIZE           = 5
BEST_OF             = 5
TEMPERATURE         = [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]   # fallback ladder

# Language-specific Whisper initial prompts
# These prime the model with domain vocabulary and prevent hallucination
INITIAL_PROMPTS = {
    "ml": (
        "Send a WhatsApp message to Deepak. "
        "Send an email to Naveen. "
        "Message HR saying I am sick. "
        "ഒരു WhatsApp സന്ദേശം അയക്കുക. "
        "ഒരു email അയക്കൂ."
    ),
    "hi": (
        "WhatsApp पर Deepak को संदेश भेजो. "
        "Naveen को email करो. "
        "HR को message करो. "
        "एक WhatsApp message भेजो."
    ),
}


# ══════════════════════════════════════════════════════════════
#  0.  GLOBAL MODEL  (loaded ONCE, reused every command)
# ══════════════════════════════════════════════════════════════

print("⏳ Loading Whisper model … (one-time startup cost)")
_whisper_model = WhisperModel(
    MODEL_PATH,
    device="cuda",
    compute_type="int8_float16",
    num_workers=1,          # parallel decode workers on the GPU
)
print("✅ Whisper model ready.")


# ══════════════════════════════════════════════════════════════
#  1.  UTILITIES
# ══════════════════════════════════════════════════════════════

@contextmanager
def silence_c_warnings():
    """Redirect C-level stderr to /dev/null (hides ALSA / JACK spam)."""
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
    """Forces a value directly into Rasa's tracker, bypassing NLU."""
    url = "http://localhost:5005/conversations/local_user/tracker/events"
    requests.post(url, json={"event": "slot", "name": slot_name, "value": slot_value})
    print(f"🧠 Slot set → '{slot_name}' = '{slot_value}'")


# ══════════════════════════════════════════════════════════════
#  2.  AUDIO PRE-PROCESSING
# ══════════════════════════════════════════════════════════════

def _butter_bandpass(low, high, fs, order=4):
    """Design a bandpass Butterworth filter (returns second-order sections)."""
    nyq = 0.5 * fs
    sos = butter(order, [low / nyq, high / nyq], btype="band", output="sos")
    return sos


def preprocess_audio(input_wav: str, output_wav: str) -> bool:
    """
    Three-stage audio clean-up pipeline:
      Stage 1 — Bandpass filter  (cuts rumble + hiss)
      Stage 2 — Noise reduction  (noisereduce spectral subtraction)
      Stage 3 — Normalisation    (consistent amplitude for Whisper)

    Returns True if audio passes the VAD check (speech detected),
    False if the clip is mostly silence and should be discarded.
    """
    # ── Read raw WAV ──────────────────────────────────────────
    with wave.open(input_wav, "rb") as wf:
        n_frames   = wf.getnframes()
        raw_bytes  = wf.readframes(n_frames)

    samples = np.frombuffer(raw_bytes, dtype=np.int16).astype(np.float32)
    fs      = SAMPLE_RATE

    # ── Stage 1 : Bandpass filter ─────────────────────────────
    sos     = _butter_bandpass(BP_LOW_HZ, BP_HIGH_HZ, fs, order=BP_ORDER)
    samples = sosfilt(sos, samples)

    # ── Stage 2 : Spectral noise reduction ───────────────────
    # Use the first NOISE_PROFILE_SEC seconds as the noise floor profile.
    # In practice the user is not yet speaking at that moment.
    profile_frames  = int(NOISE_PROFILE_SEC * fs)
    noise_clip      = samples[:profile_frames]

    samples = nr.reduce_noise(
        y                   = samples,
        y_noise             = noise_clip,
        sr                  = fs,
        prop_decrease       = NOISE_PROP_DECREASE,
        stationary          = False,   # non-stationary handles fan hum well
        n_fft               = 1024,
        hop_length          = 256,
    )

    # ── Stage 3 : Peak normalise to 90 % of int16 range ──────
    peak = np.max(np.abs(samples))
    if peak > 0:
        samples = samples / peak * (0.90 * 32767)

    cleaned_int16 = samples.astype(np.int16)

    # ── VAD check ────────────────────────────────────────────
    vad       = webrtcvad.Vad(VAD_MODE)
    frame_len = int(fs * 0.030)   # 30 ms frames
    speech_frames = 0
    total_frames  = 0

    for i in range(0, len(cleaned_int16) - frame_len, frame_len):
        frame_bytes = cleaned_int16[i : i + frame_len].tobytes()
        if len(frame_bytes) == frame_len * 2:   # 16-bit = 2 bytes/sample
            total_frames += 1
            if vad.is_speech(frame_bytes, fs):
                speech_frames += 1

    speech_ratio = speech_frames / max(total_frames, 1)
    speech_sec   = speech_frames * 0.030

    print(f"🔍 VAD: {speech_sec:.2f}s of speech detected "
          f"({speech_ratio*100:.0f}% of clip)")

    if speech_sec < VAD_MIN_SPEECH_SEC:
        print("⚠️  Too little speech detected — skipping this clip.")
        return False

    # ── Save cleaned WAV ─────────────────────────────────────
    with wave.open(output_wav, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)          # 16-bit
        wf.setframerate(fs)
        wf.writeframes(cleaned_int16.tobytes())

    print(f"✅ Cleaned audio saved → {output_wav}")
    return True


def wait_for_wake_word():
    """Listen for 'Hey Red' using Google SR (unchanged logic)."""
    recognizer = sr.Recognizer()
    with silence_c_warnings(), sr.Microphone() as source:
        print("\n💤 Cortex is sleeping. Say 'Hey Red' to wake up…")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        while True:
            try:
                audio = recognizer.listen(source, timeout=1, phrase_time_limit=3)
                text  = recognizer.recognize_google(audio).lower()
                if "nova"or "nowa" or "noval" or "no va"in text:
                    print("\n✨ [AWAKE] Cortex heard you!")
                    return True
            except sr.WaitTimeoutError:
                continue
            except sr.UnknownValueError:
                continue
            except sr.RequestError:
                print("❌ Wake word service offline. Retrying…")
                time.sleep(2)


def record_command_auto() -> bool:
    """
    Records from microphone until RIGHT SHIFT is pressed.
    Saves raw audio to AUDIO_FILENAME, then runs preprocess_audio()
    to produce CLEANED_FILENAME.  Returns False if VAD rejects the clip.
    """
    frames    = []
    recording = True

    def on_press(key):
        nonlocal recording
        if key == keyboard.Key.shift_r:
            recording = False
            return False

    listener = keyboard.Listener(on_press=on_press)
    listener.start()

    with silence_c_warnings():
        p      = pyaudio.PyAudio()
        stream = p.open(
            format           = FORMAT,
            channels         = CHANNELS,
            rate             = SAMPLE_RATE,
            input            = True,
            frames_per_buffer= CHUNK_SIZE,
        )

    print("🔴 Recording… speak now.  Press RIGHT SHIFT to finish.")

    while recording:
        data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        frames.append(data)

    print("⏹️  Stopped. Running audio clean-up pipeline…")

    stream.stop_stream()
    stream.close()
    p.terminate()

    # Save raw recording
    with wave.open(AUDIO_FILENAME, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(frames))

    # Pre-process and VAD gate
    speech_found = preprocess_audio(AUDIO_FILENAME, CLEANED_FILENAME)
    return speech_found




def translate_audio(language: str = LANGUAGE) -> str:
    """
    Translates the cleaned audio clip to English using Faster-Whisper.

    Key improvements over the original:
      • Uses the globally pre-loaded model (no reload cost)
      • beam_size=5 + best_of=5 for better accuracy
      • temperature fallback ladder handles uncertain clips
      • initial_prompt injects domain vocabulary
      • condition_on_previous_text=False prevents hallucination loops
      • vad_filter=True (Whisper's own internal VAD as a second pass)
    """
    print(f"⏳ Translating ({language.upper()} → EN) via Faster-Whisper…")

    segments, info = _whisper_model.transcribe(
        CLEANED_FILENAME,

        # ── Language & task ───────────────────────────────────
        task                      = "translate",   # always output English
        language                  = language,      # "ml" or "hi"

        # ── Decoding quality ──────────────────────────────────
        beam_size                 = BEAM_SIZE,
        best_of                   = BEST_OF,
        temperature               = TEMPERATURE,   # fallback ladder

        # ── Accuracy / hallucination prevention ───────────────
        condition_on_previous_text= False,  # no snowball hallucination
        initial_prompt            = INITIAL_PROMPTS.get(language, ""),
        no_speech_threshold       = 0.55,   # discard near-silent segments
        log_prob_threshold        = -1.0,   # reject very low-confidence

        # ── Internal VAD (second pass after our pre-processing) ─
        vad_filter                = True,
        vad_parameters            = dict(
            min_silence_duration_ms = 400,
            speech_pad_ms           = 200,
        ),

        # ── Word-level timestamps (optional but useful for debug) ─
        word_timestamps           = False,
    )

    full_text = " ".join(seg.text.strip() for seg in segments).strip()

    print(f"📊 Detected language probability: "
          f"{info.language_probability * 100:.1f}%")
    print(f"🗣️  Translated text: '{full_text}'")

    return full_text


# ══════════════════════════════════════════════════════════════
#  5.  CONVENIENCE WRAPPER  (drop-in replacement)
# ══════════════════════════════════════════════════════════════

def translate_audio_malayalam() -> str:
    """Translate Malayalam audio to English."""
    return translate_audio(language="ml")


def translate_audio_hindi() -> str:
    """Translate Hindi audio to English."""
    return translate_audio(language="hi")


if __name__ == "__main__":
    # Quick smoke-test: record one clip and translate it.
    print("\n🧪 SMOKE TEST — press RIGHT SHIFT when done speaking.\n")
    if record_command_auto():
        result = translate_audio()
        print(f"\n✅ Final result: '{result}'")
    else:
        print("❌ No usable speech detected in recording.")