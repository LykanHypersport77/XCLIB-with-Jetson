import cv2
import numpy as np
import tkinter as tk
from tkinter import filedialog
import matplotlib.pyplot as plt
import ctypes
from scipy.signal import savgol_filter

# --- Calibration Constants ---
NM_PER_PIXEL = 0.8
TOTAL_NM_RANGE = 200.0 
WINDOW_NAME = "HSIS Spectral Viewer"
MIN_WAVE_LIMIT = 525
MAX_WAVE_LIMIT = 725
INTEGRAL_SCALE = 1000000.0

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

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass 

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

def nm_to_bgr(nm):
    """Approximates the visible spectrum color for a given wavelength in BGR format."""
    r, g, b = 0.0, 0.0, 0.0
    if nm < 440:
        r = -(nm - 440) / (440 - 380)
        b = 1.0
    elif nm < 490:
        g = (nm - 440) / (490 - 440)
        b = 1.0
    elif nm < 510:
        g = 1.0
        b = -(nm - 510) / (510 - 490)
    elif nm < 580:
        r = (nm - 510) / (580 - 510)
        g = 1.0
    elif nm < 645:
        r = 1.0
        g = -(nm - 645) / (645 - 580)
    else:
        r = 1.0

    # Intensity scaling to prevent weird blowouts at the edges
    factor = 1.0
    if nm < 420: factor = 0.3 + 0.7*(nm - 380)/(420 - 380)
    elif nm > 700: factor = 0.3 + 0.7*(750 - nm)/(750 - 700)
    
    # Return as an integer tuple for OpenCV (Blue, Green, Red)
    return (int(b * factor * 255), int(g * factor * 255), int(r * factor * 255))

def extract_line_profile(box, img):
    """Extracts and averages pixel intensities across the thickness of the dispersion."""
    true_x1, true_y1, true_x2, true_y2, ux, uy, length = get_true_endpoints(box)
    if length == 0: return np.array([]), np.array([])
    
    # The base 1D line coordinates
    x_coords = np.linspace(true_x1, true_x2, int(length))
    y_coords = np.linspace(true_y1, true_y2, int(length))
    
    # Calculate perpendicular vector to sample across the "width" of the streak
    vx, vy = -uy, ux
    thickness = box['thickness']
    
    # Create spatial offsets from the center line (e.g., -2 to +2 for a thickness of 5)
    offsets = np.linspace(-thickness/2, thickness/2, thickness)
    
    h, w = img.shape[:2]
    intensity_accumulator = np.zeros(int(length))
    
    # Sweep across the thickness and accumulate the pixel values
    for offset in offsets:
        # Shift the mathematical line perpendicularly
        ox = np.round(x_coords + vx * offset).astype(int)
        oy = np.round(y_coords + vy * offset).astype(int)
        
        # Safely clip coordinates to ensure they don't fall off the image edges
        ox = np.clip(ox, 0, w - 1)
        oy = np.clip(oy, 0, h - 1)
        
        intensity_accumulator += img[oy, ox]
        
    # Average the intensities across the thickness to kill the noise
    averaged_intensities = intensity_accumulator / thickness
    
    start_nm = box['start_nm']
    
    # Subtracts the wavelength as it travels from x1 (left) to x2 (right)
    wavelengths = start_nm - (np.arange(len(averaged_intensities)) * NM_PER_PIXEL)
    
    return wavelengths, averaged_intensities

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
                
                # --- APPLY SAVITZKY-GOLAY FILTER ---
                # window_length: The number of pixels to look at at once (must be an odd number). 
                # Higher = smoother, but too high will start to flatten peaks. 15 is a great starting point.
                # polyorder: The degree of the polynomial fit (usually 2 or 3).
                smoothed_ints = savgol_filter(filtered_ints, window_length=15, polyorder=3)
                
                plt.figure(figsize=(10, 5))
                
                # Plot the raw data as a faded background line
                #plt.plot(filtered_waves, filtered_ints, color='blue', alpha=0.25, label='Raw Sensor Data')
                
                # Plot the new, smoothed data as a sharp, bold line
                plt.plot(filtered_waves, smoothed_ints, color='blue', linewidth=2, label='Sensor Data')
                
                plt.title(f"Dispersion {box['id']} Spectrum")
                plt.xlabel("Wavelength (nm)")
                plt.ylabel("Intensity")
                plt.xlim([min_nm, max_nm])
                plt.ylim(bottom=0)
                plt.legend()
                plt.grid(True)
                plt.show() 
                break

def reconstruct_image():
    """Builds the 2D spatial map using spectral integration and draws the calculated laser ray."""
    print("Reconstructing spatial image using spectral integration...")
    h, w = target_img.shape[:2]
    recon = np.zeros((h, w, 3), dtype=np.uint8)
    
    for i, box in enumerate(DISPERSIONS):
        wavelengths, intensities = extract_line_profile(box, target_img)
        if len(intensities) == 0: continue
            
        # Apply filter to smooth the data
        smoothed_ints = savgol_filter(intensities, window_length=15, polyorder=3)
        
        # --- BACKGROUND SUBTRACTION ---
        noise_floor = 5000 
        true_signal = np.maximum(smoothed_ints - noise_floor, 0)
        
        # Find the true peak wavelength
        if np.max(true_signal) > 1000: 
            max_idx = np.argmax(true_signal)
            peak_nm = wavelengths[max_idx]
        else:
            peak_nm = 0.0 
        
        # --- SPECTRAL INTEGRATION ---
        green_mask = (wavelengths >= 500) & (wavelengths <= 560)
        red_mask = (wavelengths >= 620) & (wavelengths <= 680)
        
        green_integral = np.sum(true_signal[green_mask]) if np.any(green_mask) else 0
        red_integral = np.sum(true_signal[red_mask]) if np.any(red_mask) else 0
        
        g_color = int(min((green_integral / INTEGRAL_SCALE) * 255, 255))
        r_color = int(min((red_integral / INTEGRAL_SCALE) * 255, 255))
        
        if g_color < 10 and r_color < 10:
            continue
            
        dot_color = (0, g_color, r_color) 
        
        # --- LOCATION MAPPING ---
        tx1, ty1, tx2, ty2, ux, uy, _ = get_true_endpoints(box)
        draw_x = int(tx1) 
        draw_y = int(ty1)
        
        # --- NEW: DRAW THE FULL SPECTRUM RAY ---
        # Draw the rainbow line mapping the entire 525-725nm physical space
        chunk_length = np.hypot(tx2 - tx1, ty2 - ty1)
        steps = max(2, int(chunk_length / 2))
        
        x_vals = np.linspace(tx1, tx2, steps)
        y_vals = np.linspace(ty1, ty2, steps)
        
        # wave_vals goes from 725 down to 525
        wave_vals = np.linspace(box['start_nm'], box['start_nm'] - TOTAL_NM_RANGE, steps)
        
        for k in range(steps - 1):
            p1 = (int(x_vals[k]), int(y_vals[k]))
            p2 = (int(x_vals[k+1]), int(y_vals[k+1]))
            color = nm_to_bgr(wave_vals[k])
            
            # Draw the track with thickness 2
            cv2.line(recon, p1, p2, color, 2)

        # Draw the mapped pinhole dot at the origin
        cv2.circle(recon, (draw_x, draw_y), 6, dot_color, -1)
        
        if peak_nm > 0:
            # Calculate where the laser actually hit along that rainbow line
            peak_dist = (box['start_nm'] - peak_nm) / NM_PER_PIXEL
            peak_x = int(tx1 + ux * peak_dist)
            peak_y = int(ty1 + uy * peak_dist)
            
            # Draw a bright white marker exactly where the peak strike occurred
            cv2.circle(recon, (peak_x, peak_y), 4, (255, 255, 255), -1)
            cv2.circle(recon, (peak_x, peak_y), 6, (0, 0, 0), 1) # Black outline for contrast
            
            # Draw the label slightly below the line so it doesn't cover the colors
            label_text = f"ID:{box['id']} ({draw_x}, {draw_y}) - {peak_nm:.1f}nm"
            cv2.putText(recon, label_text, (draw_x + 15, draw_y + 15), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
    # Apply Aspect Ratio Fix
    aspect_ratio = h / w 
    display_width = 1000
    display_height = int(display_width * aspect_ratio)

    cv2.namedWindow("Reconstructed Map", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Reconstructed Map", display_width, display_height)
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
