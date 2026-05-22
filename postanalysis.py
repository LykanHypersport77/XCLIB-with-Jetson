import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog, messagebox
import os

# --- Calibration Constants ---
NM_PER_PIXEL = 0.62  # spectral resolution from 8 degree prism
WINDOW_NAME = "HSIS Spectral Viewer"

# --- Dispersion Map ---
DISPERSIONS = [
    {'id': 1, 'x1': 483, 'y1': 358, 'x2': 795, 'y2': 395, 'start_nm': 525.0, 'thickness': 3},
    {'id': 2, 'x1': 356, 'y1': 433, 'x2': 615, 'y2': 460, 'start_nm': 525.0, 'thickness': 3},
]

# Global variables to hold the loaded images
target_img = None
white_img = None
dark_img = None
normalized_img_cache = None # Cache the calculation so it doesn't recalculate every slider move

def select_image(prompt):
    """Helper function to open a file dialog with a specific prompt."""
    print(f"Waiting for user to select: {prompt}")
    path = filedialog.askopenfilename(
        title=prompt,
        filetypes=[("TIFF Images", "*.tif;*.tiff"), ("All Image Files", "*.*")]
    )
    if not path:
        return None
    
    print(f"Loading {os.path.basename(path)}...")
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        print(f"Error: OpenCV could not read data at {path}")
    return img

def calculate_normalization():
    """Applies the true reflectance formula: (Target - Dark) / (White - Dark)"""
    global normalized_img_cache
    
    if target_img is None or white_img is None or dark_img is None:
        return False
        
    print("Calculating Normalized Image Matrix...")
    
    # Convert to 32-bit float for division math to prevent clipping/overflows
    target_f = target_img.astype(np.float32)
    white_f = white_img.astype(np.float32)
    dark_f = dark_img.astype(np.float32)
    
    # Subtract dark frame (floor the values at 0.0 so we don't get negative noise)
    numerator = np.maximum(target_f - dark_f, 0.0)
    denominator = np.maximum(white_f - dark_f, 1.0) # Floor at 1.0 to prevent divide by zero
    
    # Calculate Reflectance (R) - This will be a value between 0.0 and 1.0
    R = numerator / denominator
    
    # Scale it back up to the original bit depth for display
    # Assuming 12-bit data (max value 4095), but dynamically checking the dtype max just in case
    if target_img.dtype == np.uint16:
        max_val = 65535.0  # Or 4095.0 if you strictly want to cap it at 12-bit bounds
        normalized_f = np.clip(R * max_val, 0, max_val)
        normalized_img_cache = normalized_f.astype(np.uint16)
    else:
        normalized_f = np.clip(R * 255.0, 0, 255)
        normalized_img_cache = normalized_f.astype(np.uint8)
        
    print("Normalization Complete.")
    return True

def update_view(*args):
    """Triggered every time a slider is moved."""
    if target_img is None:
        return

    # Read the current positions of the sliders
    filter_active = cv2.getTrackbarPos("Filter: 0=Off, 1=On", WINDOW_NAME)
    norm_active = cv2.getTrackbarPos("Normalize: 0=Off, 1=On", WINDOW_NAME)
    min_nm = cv2.getTrackbarPos("Min Wavelength (nm)", WINDOW_NAME)
    max_nm = cv2.getTrackbarPos("Max Wavelength (nm)", WINDOW_NAME)

    # Determine which base image to use
    if norm_active == 1:
        if normalized_img_cache is None:
            # First time turning it on, do the math
            success = calculate_normalization()
            if not success:
                # Missing calibration files
                cv2.setTrackbarPos("Normalize: 0=Off, 1=On", WINDOW_NAME, 0)
                base_img = target_img.copy()
                print("Missing calibration frames. Cannot normalize.")
            else:
                base_img = normalized_img_cache.copy()
        else:
            base_img = normalized_img_cache.copy()
    else:
        base_img = target_img.copy()

    # 1. If spectral filter is off, just show the base image (normalized or raw)
    if filter_active == 0:
        cv2.imshow(WINDOW_NAME, base_img)
        return

    # Ensure Min is actually less than Max
    if min_nm > max_nm:
        cv2.setTrackbarPos("Min Wavelength (nm)", WINDOW_NAME, max_nm - 1)
        min_nm = max_nm - 1

    display_img = base_img.copy()
    blackout_mask = np.zeros(base_img.shape[:2], dtype=np.uint8)

    # 2. Apply the angled spectral slicing math
    for box in DISPERSIONS:
        x1, y1 = box['x1'], box['y1']
        x2, y2 = box['x2'], box['y2']
        start_nm = box['start_nm']
        thickness = box.get('thickness', 30)
        
        dx = x2 - x1
        dy = y2 - y1
        length = np.hypot(dx, dy)
        
        if length == 0:
            continue
            
        ux, uy = dx / length, dy / length
        vx, vy = -uy, ux
        
        # Mark full streak
        c1 = (int(x1 + vx * thickness/2), int(y1 + vy * thickness/2))
        c2 = (int(x2 + vx * thickness/2), int(y2 + vy * thickness/2))
        c3 = (int(x2 - vx * thickness/2), int(y2 - vy * thickness/2))
        c4 = (int(x1 - vx * thickness/2), int(y1 - vy * thickness/2))
        full_poly = np.array([c1, c2, c3, c4], dtype=np.int32)
        cv2.fillPoly(blackout_mask, [full_poly], 255)

        # Segment target wavelength
        d_min = (min_nm - start_nm) / NM_PER_PIXEL
        d_max = (max_nm - start_nm) / NM_PER_PIXEL
        
        d_min = max(0, min(d_min, length))
        d_max = max(0, min(d_max, length))

        if d_max > d_min:
            p_min_x, p_min_y = x1 + ux * d_min, y1 + uy * d_min
            p_max_x, p_max_y = x1 + ux * d_max, y1 + uy * d_max
            
            t1 = (int(p_min_x + vx * thickness/2), int(p_min_y + vy * thickness/2))
            t2 = (int(p_max_x + vx * thickness/2), int(p_max_y + vy * thickness/2))
            t3 = (int(p_max_x - vx * thickness/2), int(p_max_y - vy * thickness/2))
            t4 = (int(p_min_x - vx * thickness/2), int(p_min_y - vy * thickness/2))
            target_poly = np.array([t1, t2, t3, t4], dtype=np.int32)
            
            cv2.fillPoly(blackout_mask, [target_poly], 0)
            
            line_color = 65535 if base_img.dtype == np.uint16 else 255
            cv2.polylines(display_img, [target_poly], isClosed=True, color=line_color, thickness=1)

    # 3. Apply the mask to the image
    display_img[blackout_mask == 255] = 0
    cv2.imshow(WINDOW_NAME, display_img)

def main():
    global target_img, white_img, dark_img
    
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    # Prompt the user for the three distinct files
    target_img = select_image("Step 1: Select TARGET Image (The Raw Data)")
    if target_img is None: return
    
    white_img = select_image("Step 2: Select WHITE REFERENCE Image (LED Calibration)")
    if white_img is None: return
    
    dark_img = select_image("Step 3: Select DARK FRAME Image (Lens Cap On)")
    if dark_img is None: return

    # --- Setup GUI ---
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, 1200, 800)

    # Add the Normalization toggle
    cv2.createTrackbar("Normalize: 0=Off, 1=On", WINDOW_NAME, 0, 1, update_view)
    cv2.createTrackbar("Filter: 0=Off, 1=On", WINDOW_NAME, 0, 1, update_view)
    cv2.createTrackbar("Min Wavelength (nm)", WINDOW_NAME, 525, 1000, update_view)
    cv2.createTrackbar("Max Wavelength (nm)", WINDOW_NAME, 725, 1000, update_view)

    update_view()
    print("GUI is running. Toggle 'Normalize' to see the corrected data. Press 'ESC' to exit.")
    
    while True:
        key = cv2.waitKey(10)
        if key == 27:
            break
            
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
