import requests

# 1. Configuration
RASA_SERVER_URL = "http://localhost:5005/model/parse"

def get_intent_from_rasa(text_input):
    """
    Sends text to the Rasa server and returns the structured JSON.
    """
    payload = {"text": text_input}
    
    try:
        # Send the POST request to Rasa
        response = requests.post(RASA_SERVER_URL, json=payload)
        response.raise_for_status() # Check for errors
        
        # Parse the JSON
        data = response.json()
        return data
        
    except requests.exceptions.ConnectionError:
        print("❌ Error: Rasa server is not running! Run 'rasa run --enable-api' in src/nlu.")
        return None

def process_command(text):
    print(f"\n🗣️ User said: '{text}'")
    
    # Get the Brain's opinion
    nlu_data = get_intent_from_rasa(text)
    
    if not nlu_data:
        return

    # Extract Key Info
    intent = nlu_data['intent']['name']
    confidence = nlu_data['intent']['confidence']
    entities = {e['entity']: e['value'] for e in nlu_data['entities']}
    
    print(f"🧠 Intent Detected: {intent} ({confidence:.2f})")
    print(f"📦 Entities Found: {entities}")

    # --- THE DECISION TREE ---
    if intent == "send_message":
        # Check if we have everything
        platform = entities.get("platform")
        contact = entities.get("contact")
        
        if platform and contact:
            print(f"✅ SUCCESS: Ready to automate {platform} to {contact}!")
            # TODO: Call PyAutoGUI function here
        else:
            print("⚠️ MISSING DATA: We need to ask the user for more info.")

# --- TEST LOOP ---
if __name__ == "__main__":
    print("🤖 Voice Assistant Core is Running...")
    
    # Simulate a conversation
    process_command("Send a whatsapp message to Alice")
    process_command("Send a text") # This should trigger missing data logic