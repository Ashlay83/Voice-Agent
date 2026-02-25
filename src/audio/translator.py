import whisper

def translate_malayalam_to_english(audio_file_path):
    print("⏳ Loading the Whisper model into memory... (This takes a few seconds)")
    # 'base' or 'small' are good for testing on a laptop. 
    # 'small' is more accurate for regional languages like Malayalam.
    model = whisper.load_model("small") 
    
    print(f"🎙️ Processing audio: {audio_file_path}")
    
    # The magic happens here. We tell Whisper to translate the audio to English.
    result = model.transcribe(
        audio_file_path,
        task="translate",       # Forces translation to English
        language="ml"           # Tells it to expect Malayalam (optional, but makes it faster)
    )
    
    print("\n✅ Translation Complete!")
    print(f"Output: {result['text']}")
    
    return result['text']

if __name__ == "__main__":
    # Point this to a real audio file on your computer to test it
    test_audio = "test_malayalam.wav" 
    
    try:
        translated_text = translate_malayalam_to_english(test_audio)
    except FileNotFoundError:
        print(f"❌ Could not find {test_audio}. Please record a quick sample to test!")