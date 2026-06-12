import cv2
import tkinter as tk
from tkinter import filedialog

# Global variables to track clicks
points = []
disp_id = 1
img = None

def click_event(event, x, y, flags, params):
    global points, disp_id
    
    if event == cv2.EVENT_LBUTTONDOWN:
        points.append((x, y))
        cv2.circle(img, (x, y), 3, (0, 0, 255), -1)
        cv2.imshow('Calibration Mapper', img)

        # When two points are clicked, generate the dictionary line
        if len(points) == 2:
            x1, y1 = points[0]
            x2, y2 = points[1]
            
            # Prints the exact string you need for your main code
            print(f"    {{'id': {disp_id}, 'x1': {x1}, 'y1': {y1}, 'x2': {x2}, 'y2': {y2}, 'start_nm': 725, 'thickness': 5}},")
            
            # Draw a blue line to show it's mapped
            cv2.line(img, points[0], points[1], (255, 150, 0), 2)
            cv2.imshow('Calibration Mapper', img)
            
            # Reset for the next dispersion streak
            points = []
            disp_id += 1

def select_image():
    """Opens a Windows file dialog to select the image."""
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    path = filedialog.askopenfilename(
        title="Select Calibration Image",
        filetypes=[("Image Files", "*.tif;*.tiff;*.png;*.jpg"), ("All Files", "*.*")]
    )
    return path

# --- Main Execution ---
print("Waiting for you to select an image...")
image_path = select_image()

if not image_path:
    print("No image selected. Exiting.")
else:
    img = cv2.imread(image_path)
    
    if img is None:
        print(f"Error: OpenCV could not read the file. It might be corrupted.")
    else:
        print("\n--- Calibration Mapper Active ---")
        print("1. Click the START of a dispersion streak (x1, y1)")
        print("2. Click the END of that same streak (x2, y2)")
        print("3. Check your terminal for the formatted output!")
        print("Press ESC to close the window.")
        
        cv2.imshow('Calibration Mapper', img)
        cv2.setMouseCallback('Calibration Mapper', click_event)
        
        while True:
            key = cv2.waitKey(10)
            if key == 27: # ESC key to exit
                break
                
        cv2.destroyAllWindows()