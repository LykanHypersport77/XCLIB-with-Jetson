import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog
import matplotlib.pyplot as plt

# --- Calibration Constants ---
NM_PER_PIXEL = 0.8
TOTAL_NM_RANGE = 200.0 
WINDOW_NAME = "HSIS Spectral Viewer"
MIN_WAVE_LIMIT = 525
MAX_WAVE_LIMIT = 725

# --- Manual Dispersion Map ---
DISPERSIONS = [
    {'id': 1, 'x1': 615, 'y1': 284, 'x2': 790, 'y2': 271, 'start_nm': 725, 'thickness': 5},
    {'id': 2, 'x1': 595, 'y1': 298, 'x2': 734, 'y2': 289, 'start_nm': 725, 'thickness': 5},
    {'id': 3, 'x1': 575, 'y1': 312, 'x2': 737, 'y2': 302, 'start_nm': 725, 'thickness': 5},
    {'id': 4, 'x1': 555, 'y1': 322, 'x2': 698, 'y2': 314, 'start_nm': 725, 'thickness': 5},
    {'id': 5, 'x1': 535, 'y1': 335, 'x2': 694, 'y2': 325, 'start_nm': 725, 'thickness': 5},

    {'id': 10, 'x1': 520, 'y1': 694, 'x2': 624, 'y2': 691, 'start_nm': 725, 'thickness': 5},
    {'id': 9, 'x1': 540, 'y1': 685, 'x2': 626, 'y2': 682, 'start_nm': 725, 'thickness': 5},
    {'id': 8, 'x1': 560, 'y1': 676, 'x2': 643, 'y2': 672, 'start_nm': 725, 'thickness': 5},
    {'id': 7, 'x1': 580, 'y1': 666, 'x2': 670, 'y2': 662, 'start_nm': 725, 'thickness': 5},
    {'id': 6, 'x1': 600, 'y1': 652, 'x2': 765, 'y2': 645, 'start_nm': 725, 'thickness': 5},

    {'id': 11, 'x1': 500, 'y1': 705, 'x2': 640, 'y2': 700, 'start_nm': 725, 'thickness': 5},
]
target_img = None

def select_image(prompt):
    print(f"Waiting for user to select: {prompt}")
    path = filedialog.askopenfilename(
        title=prompt,
        filetypes=[("Image Files", "*.tif;*.tiff;*.png;*.jpg"), ("All Files", "*.*")]
    )
    if not path: return None
    return cv2.imread(path, cv2.IMREAD_GRAYSCALE | cv2.IMREAD_ANYDEPTH)

def get_true_endpoints(box):
    """Calculates the exact pixel endpoints, anchoring the start exactly at x1, y1."""
    x1, y1, x2, y2 = box['x1'], box['y1'], box['x2'], box['y2']
    dx, dy = x2 - x1, y2 - y1
    guide_length = np.hypot(dx, dy)
    
    if guide_length == 0: 
        return x1, y1, x2, y2, 0, 0, 0
        
    ux, uy = dx/guide_length, dy/guide_length
    
    fixed_length_pixels = TOTAL_NM_RANGE / NM_PER_PIXEL
    
    true_x1 = float(x1)
    true_y1 = float(y1)
    true_x2 = x1 + (ux * fixed_length_pixels)
    true_y2 = y1 + (uy * fixed_length_pixels)
    
    return true_x1, true_y1, true_x2, true_y2, ux, uy, fixed_length_pixels

def extract_line_profile(box, img):
    """Extracts the pixel intensities using the dynamically calculated endpoints."""
    true_x1, true_y1, true_x2, true_y2, _, _, length = get_true_endpoints(box)
    if length == 0: return np.array([]), np.array([])
    
    x_coords = np.linspace(true_x1, true_x2, int(length)).astype(int)
    y_coords = np.linspace(true_y1, true_y2, int(length)).astype(int)
    
    h, w = img.shape[:2]
    valid = (x_coords >= 0) & (x_coords < w) & (y_coords >= 0) & (y_coords < h)
    x_coords, y_coords = x_coords[valid], y_coords[valid]
    
    if len(x_coords) == 0: return np.array([]), np.array([])
    
    intensities = img[y_coords, x_coords]
    start_nm = box['start_nm']
    
    # --- FLIPPED MATH ---
    # Subtracts the wavelength as it travels from x1 (left) to x2 (right)
    wavelengths = start_nm - (np.arange(len(intensities)) * NM_PER_PIXEL)
    
    return wavelengths, intensities

def on_mouse_click(event, x, y, flags, param):
    """Detects clicks near the blue dispersion lines."""
    if event == cv2.EVENT_LBUTTONDOWN:
        min_nm = cv2.getTrackbarPos("Min(nm)", WINDOW_NAME)
        max_nm = cv2.getTrackbarPos("Max(nm)", WINDOW_NAME)

        for box in DISPERSIONS:
            tx1, ty1, tx2, ty2, _, _, _ = get_true_endpoints(box)
            
            min_x, max_x = min(tx1, tx2), max(tx1, tx2)
            
            click_tolerance = 15 
            min_y = min(ty1, ty2) - click_tolerance
            max_y = max(ty1, ty2) + click_tolerance
            
            if min_x <= x <= max_x and min_y <= y <= max_y:
                print(f"Plotting Graph for Dispersion ID: {box['id']} ({min_nm}nm - {max_nm}nm)")
                
                wavelengths, intensities = extract_line_profile(box, target_img)
                
                valid_mask = (wavelengths >= min_nm) & (wavelengths <= max_nm)
                filtered_waves = wavelengths[valid_mask]
                filtered_ints = intensities[valid_mask]
                
                if len(filtered_waves) == 0:
                    print("Error: Selected range contains no data for this dispersion.")
                    break
                
                plt.figure(figsize=(10, 5))
                plt.plot(filtered_waves, filtered_ints, color='blue')
                plt.title(f"Dispersion {box['id']} Spectrum")
                plt.xlabel("Wavelength (nm)")
                plt.ylabel("Intensity")
                plt.xlim([min_nm, max_nm])
                plt.grid(True)
                plt.show() 
                break

def reconstruct_image():
    """Builds the 2D spatial map matching the exact dimensions of the raw image."""
    print("Reconstructing spatial image...")
    h, w = target_img.shape[:2]
    recon = np.zeros((h, w, 3), dtype=np.uint8)
    
    for i, box in enumerate(DISPERSIONS):
        wavelengths, intensities = extract_line_profile(box, target_img)
        if len(intensities) == 0: continue
            
        max_idx = np.argmax(intensities)
        peak_intensity = intensities[max_idx]
        peak_nm = wavelengths[max_idx]
        
        if peak_intensity > 20000: 
            
            # --- Dynamic Brightness ---
            brightness = int(min((peak_intensity / 50000.0) * 255, 255))
            
            # Default to a grayscale dot based on intensity
            color = (brightness, brightness, brightness) 
            
            # OpenCV uses BGR (Blue, Green, Red) format
            if 500 < peak_nm < 560: 
                color = (0, brightness, 0) # Green
            elif 620 < peak_nm < 680: 
                color = (0, 0, brightness) # Red
                
            tx1, ty1, tx2, ty2, _, _, _ = get_true_endpoints(box)
            draw_y = int((ty1 + ty2) / 2)
            draw_x = int(w / 3) 
            
            cv2.circle(recon, (draw_x, draw_y), 20, color, -1)
            cv2.putText(recon, f"ID:{box['id']} - {peak_nm:.1f}nm", (draw_x + 35, draw_y + 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            
    cv2.namedWindow("Reconstructed Map", cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow("Reconstructed Map", w, h)
    cv2.imshow("Reconstructed Map", recon)

def update_view(*args):
    """Renders the dynamic blue lines that resize with the slider."""
    if target_img is None: return

    overlays = cv2.getTrackbarPos("Overlays", WINDOW_NAME)
    hide_bg = cv2.getTrackbarPos("Hide BG", WINDOW_NAME)
    min_nm = cv2.getTrackbarPos("Min(nm)", WINDOW_NAME)
    max_nm = cv2.getTrackbarPos("Max(nm)", WINDOW_NAME)

    if min_nm < MIN_WAVE_LIMIT:
        cv2.setTrackbarPos("Min(nm)", WINDOW_NAME, MIN_WAVE_LIMIT)
        min_nm = MIN_WAVE_LIMIT
    if max_nm > MAX_WAVE_LIMIT:
        cv2.setTrackbarPos("Max(nm)", WINDOW_NAME, MAX_WAVE_LIMIT)
        max_nm = MAX_WAVE_LIMIT
    if min_nm >= max_nm:
        cv2.setTrackbarPos("Min(nm)", WINDOW_NAME, max_nm - 1)
        min_nm = max_nm - 1

    if target_img.dtype == np.uint16:
        base = cv2.normalize(target_img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    else:
        base = target_img.copy()
    display_img = cv2.cvtColor(base, cv2.COLOR_GRAY2BGR)
    
    mask = np.ones(base.shape[:2], dtype=np.uint8) * 255
    if hide_bg == 1:
        mask = np.zeros(base.shape[:2], dtype=np.uint8)

    for box in DISPERSIONS:
        tx1, ty1, tx2, ty2, ux, uy, length = get_true_endpoints(box)
        if length == 0: continue
        
        start_nm, thickness = box['start_nm'], box['thickness']
        vx, vy = -uy, ux
        
        # --- FLIPPED CROP MATH ---
        # Because x1 is the highest wavelength (725), the distance to max_nm (e.g. 700) 
        # is physically shorter than the distance to min_nm (e.g. 525).
        d_min_draw = max(0, min((start_nm - max_nm) / NM_PER_PIXEL, length))
        d_max_draw = max(0, min((start_nm - min_nm) / NM_PER_PIXEL, length))
        
        if d_max_draw > d_min_draw:
            draw_x1, draw_y1 = tx1 + ux*d_min_draw, ty1 + uy*d_min_draw
            draw_x2, draw_y2 = tx1 + ux*d_max_draw, ty1 + uy*d_max_draw
            
            if hide_bg == 1:
                c1 = (int(draw_x1 + vx * thickness/2), int(draw_y1 + vy * thickness/2))
                c2 = (int(draw_x2 + vx * thickness/2), int(draw_y2 + vy * thickness/2))
                c3 = (int(draw_x2 - vx * thickness/2), int(draw_y2 - vy * thickness/2))
                c4 = (int(draw_x1 - vx * thickness/2), int(draw_y1 - vy * thickness/2))
                cv2.fillPoly(mask, [np.array([c1, c2, c3, c4], dtype=np.int32)], 255)
                
            if overlays == 1:
                blue_color = (255, 150, 0)
                cv2.line(display_img, (int(draw_x1), int(draw_y1)), (int(draw_x2), int(draw_y2)), blue_color, 1)
                
                # Pinned the ID text to the absolute start of the streak (tx1) so it doesn't move when cropping
                cv2.putText(display_img, f"ID:{box['id']}", (int(tx1), int(ty1) - 8), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, blue_color, 1)

    if hide_bg == 1:
        display_img = cv2.bitwise_and(display_img, display_img, mask=mask)

    if overlays == 1:
        overlay = display_img.copy()
        h, w = display_img.shape[:2]
        cv2.rectangle(overlay, (0, 0), (w, 35), (20, 20, 20), -1)
        display_img = cv2.addWeighted(overlay, 0.85, display_img, 0.15, 0)
        
        mode_text = "MODE: RAW"
        if hide_bg == 1: mode_text = "MODE: BACKGROUND HIDDEN"
        status_text = f"{mode_text}   |   RANGE: {min_nm}nm - {max_nm}nm   |   BOX LENGTH: {TOTAL_NM_RANGE}nm"
        
        cv2.putText(display_img, status_text, (15, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)

    cv2.imshow(WINDOW_NAME, display_img)

def main():
    global target_img
    
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    target_img = select_image("Select RAW Target Image")
    if target_img is None: return

    h, w = target_img.shape[:2]

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO)
    cv2.resizeWindow(WINDOW_NAME, w, h)
    
    cv2.createTrackbar("Overlays", WINDOW_NAME, 1, 1, update_view)
    cv2.createTrackbar("Hide BG", WINDOW_NAME, 0, 1, update_view)
    cv2.createTrackbar("Min(nm)", WINDOW_NAME, MIN_WAVE_LIMIT, MAX_WAVE_LIMIT, update_view)
    cv2.createTrackbar("Max(nm)", WINDOW_NAME, MAX_WAVE_LIMIT, MAX_WAVE_LIMIT, update_view)

    cv2.setMouseCallback(WINDOW_NAME, on_mouse_click)

    update_view()
    
    print("--- HSIS Viewer Active ---")
    print("- LEFT CLICK near a blue line to see the spectral graph.")
    print("- PRESS 'R' to generate the Reconstructed Image.")
    print("- PRESS 'ESC' to exit.")
    
    while True:
        key = cv2.waitKey(10)
        if key == 27: 
            break
        elif key == ord('r') or key == ord('R'):
            reconstruct_image()
            
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
