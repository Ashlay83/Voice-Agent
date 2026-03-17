import pyautogui
import time

def wait_and_click(image_path, timeout=20, click=True):
    """Scans the screen for an image and clicks it."""
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