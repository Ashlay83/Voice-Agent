import pyautogui
import time
from src.gui.screen_tools import wait_and_click

def automate_email(email_address, message):
    """Drives the browser to send an Email via Gmail using direct visual clicks."""
    print("\n📧 STARTING VISUAL EMAIL AUTOMATION...")
    
    # 1. Open Browser & Navigate
    if not wait_and_click("assets/browser_icon.png"): return
    time.sleep(1) 
    print("⌨️ Pressing Ctrl+T for New Tab...")
    pyautogui.hotkey('ctrl', 't')
    time.sleep(1)
    
    print("⌨️ Navigating to Gmail...")
    pyautogui.write("https://mail.google.com", interval=0.05)
    pyautogui.press("enter")
    
    # 2. Click Compose
    print("⏳ Waiting for Inbox to load...")
    time.sleep(5) # Give the inbox plenty of time to render
    if not wait_and_click("assets/compose_button.png", timeout=30): return
    time.sleep(2) # Wait for the pop-up window to fully appear
    
    # 3. Click 'To' and Type
    print(f"🎯 Locating 'To' field for: {email_address}")
    if not wait_and_click("assets/to_field.png", timeout=10): return
    pyautogui.write(email_address, interval=0.05)
    time.sleep(1)
    pyautogui.press("enter") # Locks the email pill into place
    
    # 4. Click 'Subject' and Type
    print("🎯 Locating 'Subject' field...")
    if not wait_and_click("assets/subject_field.png", timeout=5): return
    pyautogui.write("Voice Message from Cortex", interval=0.05)
    time.sleep(0.5)
    
    # 5. Click 'Message Body' and Type
    print("🎯 Locating Message Body...")
    if not wait_and_click("assets/message_body.png", timeout=5): return
    pyautogui.write(message, interval=0.05)
    time.sleep(1)
    
    # 6. Click the Blue Send Button
    print("🚀 Clicking Send...")
    if not wait_and_click("assets/send_button_email.png", timeout=5): return
    
    print("✅ EMAIL SENT SUCCESSFULLY!")