import pyautogui
import time

def find_and_click(image_path):
    print(f"👀 Scanning screen for {image_path}...")
    
    try:
        # locateCenterOnScreen finds the exact (X,Y) coordinates of your template
        location = pyautogui.locateCenterOnScreen(image_path, confidence=0.8)
        
        if location:
            print(f"🎯 Target found at: {location.x}, {location.y}")
            # Move the mouse to the target and click it
            pyautogui.moveTo(location.x, location.y, duration=0.5)
            pyautogui.click()
            return True
        else:
            print(f"❌ Target not found. Is the item visible on screen?")
            return False
            
    except pyautogui.ImageNotFoundException:
        print(f"❌ Image not found on screen. Check your screenshot!")
        return False

if __name__ == "__main__":
    print("⏲️ Switch to the screen you want to test! You have 3 seconds...")
    time.sleep(3)
    
    # Put the name of the asset you want to test here. 
    # Let's test the WhatsApp bookmark first.
    test_image = "assets/whatsapp_bookmark.png"
    
    find_and_click(test_image)