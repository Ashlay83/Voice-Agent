import pyautogui
import time
from src.gui.screen_tools import wait_and_click

def automate_whatsapp(contact, message):
    """Drives the browser to send a WhatsApp message."""
    print("\n🚀 STARTING WHATSAPP AUTOMATION...")
    
    if not wait_and_click("assets/browser_icon.png"): return
    time.sleep(1) 
    
    print("⌨️ Pressing Ctrl+T for New Tab...")
    pyautogui.hotkey('ctrl', 't')
    time.sleep(1)
    
    if not wait_and_click("assets/whatsapp_bookmark.png"): return
    print("⏳ Waiting for WhatsApp Web to load...")
    
    if not wait_and_click("assets/search_bar.png", timeout=30): return
    
    pyautogui.write(contact, interval=0.1)
    time.sleep(1.5) 
    pyautogui.press("enter")
    
    print("⌨️ Typing the message...")
    time.sleep(1) 
    pyautogui.write(message, interval=0.05)
    time.sleep(0.5)
    pyautogui.press("enter")
    print("✅ WHATSAPP MESSAGE SENT SUCCESSFULLY!")