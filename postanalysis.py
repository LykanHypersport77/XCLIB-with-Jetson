import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog
import os

# --- Calibration Constants ---
NM_PER_PIXEL = 0.62  # spectral resolution from 8 degree prism
WINDOW_NAME = "HSIS Spectral Viewer"

# --- Dispersion Map ---
# x1, y1 is the START of the streak (centerline)
# x2, y2 is the END of the streak (centerline)
# 'thickness' is how wide the bounding box should be (in pixels)
DISPERSIONS = [
    {'id': 1, 'x1': 483, 'y1': 358, 'x2': 795, 'y2': 395, 'start_nm': 525.0, 'thickness': 3},
    {'id': 2, 'x1': 356, 'y1': 433, 'x2': 615, 'y2': 460, 'start_nm': 525.0, 'thickness': 3},
]

# Global variable to hold the loaded image
original_img = None

def update_view(*args):
    """
    Triggered every time a slider is moved.
    Reads the slider values, calculates the angled polygons, and updates the view.
    """
    if original_img is None:
        return

    # Read the current positions of the sliders
    filter_active = cv2.getTrackbarPos("Filter: 0=Off, 1=On", WINDOW_NAME)
    min_nm = cv2.getTrackbarPos("Min Wavelength (nm)", WINDOW_NAME)
    max_nm = cv2.getTrackbarPos("Max Wavelength (nm)", WINDOW_NAME)

    # 1. If filter is off, just show the raw image
    if filter_active == 0:
        cv2.imshow(WINDOW_NAME, original_img)
        return

    # Ensure Min is actually less than Max
    if min_nm > max_nm:
        cv2.setTrackbarPos("Min Wavelength (nm)", WINDOW_NAME, max_nm - 1)
        min_nm = max_nm - 1

    # Copy the original image so we keep the background intact
    display_img = original_img.copy()
    
    # Create a mask to hold the areas we want to BLACK OUT
    blackout_mask = np.zeros(original_img.shape[:2], dtype=np.uint8)

    # 2. Apply the angled spectral slicing math
    for box in DISPERSIONS:
        x1, y1 = box['x1'], box['y1']
        x2, y2 = box['x2'], box['y2']
        start_nm = box['start_nm']
        thickness = box.get('thickness', 30) # Default to 30 if not defined
        
        # --- Vector Math for the Angle ---
        dx = x2 - x1
        dy = y2 - y1
        length = np.hypot(dx, dy)
        
        if length == 0:
            continue # Prevent division by zero if coordinates are identical
            
        # Unit vector along the line (direction)
        ux, uy = dx / length, dy / length
        # Perpendicular unit vector (for thickness)
        vx, vy = -uy, ux
        
        # Step A: Mark the ENTIRE dispersion streak to be blacked out
        # We calculate the 4 corners of the full tilted box
        c1 = (int(x1 + vx * thickness/2), int(y1 + vy * thickness/2))
        c2 = (int(x2 + vx * thickness/2), int(y2 + vy * thickness/2))
        c3 = (int(x2 - vx * thickness/2), int(y2 - vy * thickness/2))
        c4 = (int(x1 - vx * thickness/2), int(y1 - vy * thickness/2))
        full_poly = np.array([c1, c2, c3, c4], dtype=np.int32)
        
        # Add the full streak to the blackout mask
        cv2.fillPoly(blackout_mask, [full_poly], 255)

        # Step B: Calculate the specific target wavelength segment
        # Find the distance along the line for our min and max wavelengths
        d_min = (min_nm - start_nm) / NM_PER_PIXEL
        d_max = (max_nm - start_nm) / NM_PER_PIXEL
        
        # Clamp the distances so they don't draw outside the defined line length
        d_min = max(0, min(d_min, length))
        d_max = max(0, min(d_max, length))

        # Step C: If the target range exists within this streak, "cut it out" of the blackout mask
        if d_max > d_min:
            # Find exact center points along the line for min and max
            p_min_x, p_min_y = x1 + ux * d_min, y1 + uy * d_min
            p_max_x, p_max_y = x1 + ux * d_max, y1 + uy * d_max
            
            # Calculate the 4 corners of the targeted wavelength polygon
            t1 = (int(p_min_x + vx * thickness/2), int(p_min_y + vy * thickness/2))
            t2 = (int(p_max_x + vx * thickness/2), int(p_max_y + vy * thickness/2))
            t3 = (int(p_max_x - vx * thickness/2), int(p_max_y - vy * thickness/2))
            t4 = (int(p_min_x - vx * thickness/2), int(p_min_y - vy * thickness/2))
            target_poly = np.array([t1, t2, t3, t4], dtype=np.int32)
            
            # Draw black (0) over the target area in the mask to SAVE those pixels
            cv2.fillPoly(blackout_mask, [target_poly], 0)
            
            # Optional visual aid: Draw a faint outline around the target box so you can see the math working
            # Determine line color based on image bit-depth (8-bit vs 16-bit TIFF)
            line_color = 65535 if original_img.dtype == np.uint16 else 255
            cv2.polylines(display_img, [target_poly], isClosed=True, color=line_color, thickness=1)

    # 3. Apply the mask to the image
    # Any pixel where the blackout mask is 255 gets set to 0 (black)
    display_img[blackout_mask == 255] = 0
            
    # Display the filtered result
    cv2.imshow(WINDOW_NAME, display_img)

def main():
    global original_img
    
    # --- File Picker GUI ---
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    print("Waiting for image selection...")
    image_path = filedialog.askopenfilename(
        title="Select Hyperspectral Image",
        filetypes=[
            ("TIFF Images", "*.tif;*.tiff"), 
            ("All Image Files", "*.tif;*.tiff;*.png;*.jpg;*.bmp"),
            ("All Files", "*.*")
        ]
    )
    
    if not image_path:
        print("No file selected. Exiting script.")
        return
        
    print(f"Loading: {os.path.basename(image_path)}")

    # --- Load Image ---
    # IMREAD_UNCHANGED preserves your 12-bit/16-bit scientific TIFF data
    original_img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    
    if original_img is None:
        print(f"Error: OpenCV could not read the image data at {image_path}")
        return

    # --- Setup the Main OpenCV GUI Window ---
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, 1200, 800)

    # --- Create Trackbars (Sliders) ---
    cv2.createTrackbar("Filter: 0=Off, 1=On", WINDOW_NAME, 0, 1, update_view)
    cv2.createTrackbar("Min Wavelength (nm)", WINDOW_NAME, 525, 1000, update_view)
    cv2.createTrackbar("Max Wavelength (nm)", WINDOW_NAME, 725, 1000, update_view)

    # Force the first frame to draw
    update_view()

    print("GUI is running. Press the 'ESC' key while the window is selected to close it.")
    
    while True:
        key = cv2.waitKey(10)
        if key == 27:
            break
            
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()