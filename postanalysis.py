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
GRID_WINDOW_NAME = "Hyperspectral reconstruction"
MIN_WAVE_LIMIT = 525
MAX_WAVE_LIMIT = 725

# Tweak this number to make the reconstructed grid blocks brighter or darker
INTEGRAL_SCALE = 500000.0 

# --- Manual Dispersion Map ---
DISPERSIONS = [
    {'id': 1, 'x1': 725, 'y1': 102, 'x2': 911, 'y2': 76, 'start_nm': 725, 'thickness': 3},
    {'id': 2, 'x1': 705, 'y1': 120, 'x2': 857, 'y2': 98, 'start_nm': 725, 'thickness': 3},
    {'id': 3, 'x1': 685, 'y1': 132, 'x2': 828, 'y2': 117, 'start_nm': 725, 'thickness': 3},
    {'id': 4, 'x1': 665, 'y1': 146, 'x2': 828, 'y2': 134, 'start_nm': 725, 'thickness': 3},
    {'id': 5, 'x1': 645, 'y1': 162, 'x2': 811, 'y2': 152, 'start_nm': 725, 'thickness': 3},
    {'id': 6, 'x1': 625, 'y1': 178, 'x2': 754, 'y2': 169, 'start_nm': 725, 'thickness': 3},
    {'id': 7, 'x1': 605, 'y1': 191, 'x2': 712, 'y2': 184, 'start_nm': 725, 'thickness': 3},
    {'id': 8, 'x1': 585, 'y1': 207, 'x2': 701, 'y2': 197, 'start_nm': 725, 'thickness': 3},

    {'id': 11, 'x1': 655, 'y1': 256, 'x2': 790, 'y2': 241, 'start_nm': 725, 'thickness': 3},
    {'id': 12, 'x1': 635, 'y1': 270, 'x2': 790, 'y2': 256, 'start_nm': 725, 'thickness': 3},
    {'id': 13, 'x1': 615, 'y1': 284, 'x2': 790, 'y2': 271, 'start_nm': 725, 'thickness': 3},
    {'id': 14, 'x1': 595, 'y1': 298, 'x2': 734, 'y2': 289, 'start_nm': 725, 'thickness': 3},
    {'id': 15, 'x1': 575, 'y1': 312, 'x2': 737, 'y2': 302, 'start_nm': 725, 'thickness': 3},
    {'id': 16, 'x1': 555, 'y1': 322, 'x2': 698, 'y2': 314, 'start_nm': 725, 'thickness': 3},
    {'id': 17, 'x1': 535, 'y1': 335, 'x2': 694, 'y2': 325, 'start_nm': 725, 'thickness': 3},
    {'id': 18, 'x1': 515, 'y1': 350, 'x2': 690, 'y2': 340, 'start_nm': 725, 'thickness': 3},

    {'id': 41, 'x1': 520, 'y1': 694, 'x2': 624, 'y2': 691, 'start_nm': 725, 'thickness': 3},
    {'id': 42, 'x1': 540, 'y1': 685, 'x2': 626, 'y2': 682, 'start_nm': 725, 'thickness': 3},
    {'id': 43, 'x1': 560, 'y1': 676, 'x2': 643, 'y2': 672, 'start_nm': 725, 'thickness': 3},
    {'id': 44, 'x1': 580, 'y1': 666, 'x2': 670, 'y2': 662, 'start_nm': 725, 'thickness': 3},
    {'id': 45, 'x1': 600, 'y1': 652, 'x2': 765, 'y2': 645, 'start_nm': 725, 'thickness': 3},
    {'id': 46, 'x1': 500, 'y1': 705, 'x2': 640, 'y2': 700, 'start_nm': 725, 'thickness': 3},
]
target_img = None
target_img_8u = None # Added a cached 8-bit version of the image

# Defeat Windows Display Scaling
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass 

def select_image(prompt):
    """Opens a Windows file dialog securely and uniquely."""
    print(f"Waiting for user to select: {prompt}")
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    
    path = filedialog.askopenfilename(
        title=prompt,
        filetypes=[("Image Files", "*.tif;*.tiff;*.png;*.jpg"), ("All Files", "*.*")]
    )
    
    root.destroy()
    
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
    """Extracts and averages pixel intensities across the thickness of the dispersion."""
    true_x1, true_y1, true_x2, true_y2, ux, uy, length = get_true_endpoints(box)
    if length == 0: return np.array([]), np.array([])
    
    x_coords = np.linspace(true_x1, true_x2, int(length))
    y_coords = np.linspace(true_y1, true_y2, int(length))
    
    vx, vy = -uy, ux
    thickness = box['thickness']
    offsets = np.linspace(-thickness/2, thickness/2, thickness)
    
    h, w = img.shape[:2]
    intensity_accumulator = np.zeros(int(length))
    
    for offset in offsets:
        ox = np.round(x_coords + vx * offset).astype(int)
        oy = np.round(y_coords + vy * offset).astype(int)
        ox = np.clip(ox, 0, w - 1)
        oy = np.clip(oy, 0, h - 1)
        intensity_accumulator += img[oy, ox]
        
    averaged_intensities = intensity_accumulator / thickness
    start_nm = box['start_nm']
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
                
                smoothed_ints = savgol_filter(filtered_ints, window_length=15, polyorder=3)
                
                plt.figure(figsize=(10, 5))
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

def draw_grid_canvas(*args):
    """Generates the grid, applies spacing, and auto-scales the window."""
    
    TOTAL_ROWS = 8
    TOTAL_COLS = 10
    CELL_W = int(TOTAL_NM_RANGE / NM_PER_PIXEL) 
    CELL_H = 15 

    PAD_X = 20 
    PAD_Y = 35 
    # ==========================================
    
    # ==========================================
    # STEP 1: VECTOR CROP (TIGHT GRID)
    # ==========================================
    tight_grid = np.zeros((100 * CELL_H, CELL_W), dtype=np.uint8)
    
    min_nm = cv2.getTrackbarPos("Min(nm)", GRID_WINDOW_NAME)
    max_nm = cv2.getTrackbarPos("Max(nm)", GRID_WINDOW_NAME)
    
    if min_nm >= max_nm:
        cv2.setTrackbarPos("Min(nm)", GRID_WINDOW_NAME, max_nm - 1)
        min_nm = max_nm - 1
        
    valid_ids = [box['id'] for box in DISPERSIONS]
    
    for box in DISPERSIONS:
        tight_y = (box['id'] - 1) * CELL_H
        
        tx1, ty1, tx2, ty2, ux, uy, length = get_true_endpoints(box)
        if length == 0: continue
            
        start_px = int(max(0, (box['start_nm'] - max_nm) / NM_PER_PIXEL))
        end_px = int(min(length, (box['start_nm'] - min_nm) / NM_PER_PIXEL))
        
        if start_px >= end_px: continue
            
        thickness = box['thickness']
        num_pixels = end_px - start_px
        
        base_x = tx1 + ux * start_px
        base_y = ty1 + uy * start_px
        
        x_coords = base_x + ux * np.arange(num_pixels)
        y_coords = base_y + uy * np.arange(num_pixels)
        
        vx, vy = -uy, ux
        offsets = np.linspace(-thickness/2, thickness/2, thickness)
        
        slice_canvas = np.zeros((thickness, CELL_W), dtype=np.uint8)
        h, w = target_img_8u.shape[:2]
        
        for r, offset in enumerate(offsets):
            ox = np.round(x_coords + vx * offset).astype(int)
            oy = np.round(y_coords + vy * offset).astype(int)
            
            ox = np.clip(ox, 0, w - 1)
            oy = np.clip(oy, 0, h - 1)
            
            slice_canvas[r, start_px:end_px] = target_img_8u[oy, ox]

        mask = np.zeros((thickness, CELL_W), dtype=np.uint8)
        mask[:, start_px:end_px] = 255
        filtered_slice = cv2.bitwise_and(slice_canvas, mask)

        draw_y_start = tight_y + (CELL_H - thickness) // 2
        tight_grid[draw_y_start:draw_y_start + thickness, 0:CELL_W] = filtered_slice

    tight_grid_color = cv2.cvtColor(tight_grid, cv2.COLOR_GRAY2BGR)

    # ==========================================
    # STEP 2: THE SPACING LAYOUT ENGINE
    # ==========================================
    padded_w = (TOTAL_COLS * CELL_W) + ((TOTAL_COLS + 1) * PAD_X)
    padded_h = (TOTAL_ROWS * CELL_H) + ((TOTAL_ROWS + 1) * PAD_Y)
    padded_grid = np.zeros((padded_h, padded_w, 3), dtype=np.uint8)

    for r in range(TOTAL_ROWS):
        for c in range(TOTAL_COLS):
            box_id = (r * TOTAL_COLS) + ((TOTAL_COLS - 1) - c) + 1
            
            tight_y = (box_id - 1) * CELL_H
            cell_data = tight_grid_color[tight_y:tight_y + CELL_H, 0:CELL_W]
            
            paste_x = PAD_X + c * (CELL_W + PAD_X)
            paste_y = PAD_Y + r * (CELL_H + PAD_Y)
            padded_grid[paste_y:paste_y + CELL_H, paste_x:paste_x + CELL_W] = cell_data
            
            if box_id in valid_ids:
                cv2.rectangle(padded_grid, (paste_x, paste_y), (paste_x + CELL_W, paste_y + CELL_H), (60, 60, 60), 1)
                cv2.putText(padded_grid, str(box_id), (paste_x + 5, paste_y + 12), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (150, 150, 150), 1)

    # Automatically size the window to perfectly match the padded grid!
    aspect = padded_grid.shape[0] / padded_grid.shape[1]
    cv2.resizeWindow(GRID_WINDOW_NAME, 1400, int(1400 * aspect))
    cv2.imshow(GRID_WINDOW_NAME, padded_grid)


def reconstruct_grid():
    """Launches the window, sizes it correctly first, then hooks up the live UI sliders."""
    print(f"Launching Live Visual Grid: {GRID_WINDOW_NAME}...")
    
    # 1. Create the window
    cv2.namedWindow(GRID_WINDOW_NAME, cv2.WINDOW_NORMAL)
    
    # 2. Force the window to be large IMMEDIATELY, before adding sliders!
    PAD_X, PAD_Y = 20, 35
    CELL_W = int(TOTAL_NM_RANGE / NM_PER_PIXEL) 
    CELL_H = 15
    canvas_w = 10 * (CELL_W + PAD_X)
    canvas_h = 8 * (CELL_H + PAD_Y)
    aspect = canvas_h / canvas_w
    
    # Resize the window to full width (1400px) first
    cv2.resizeWindow(GRID_WINDOW_NAME, 1400, int(1400 * aspect))
    
    # Grab initial slider values from the main window
    initial_min = cv2.getTrackbarPos("Min(nm)", WINDOW_NAME)
    initial_max = cv2.getTrackbarPos("Max(nm)", WINDOW_NAME)
    
    # 3. NOW create the trackbars on the large window
    cv2.createTrackbar("Min(nm)", GRID_WINDOW_NAME, MIN_WAVE_LIMIT, MAX_WAVE_LIMIT, draw_grid_canvas)
    cv2.createTrackbar("Max(nm)", GRID_WINDOW_NAME, MAX_WAVE_LIMIT, MAX_WAVE_LIMIT, draw_grid_canvas)
    
    # 4. Set their values
    cv2.setTrackbarPos("Min(nm)", GRID_WINDOW_NAME, initial_min)
    cv2.setTrackbarPos("Max(nm)", GRID_WINDOW_NAME, initial_max)
    
    # Trigger the first render
    draw_grid_canvas(0)

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

    display_img = cv2.cvtColor(target_img_8u, cv2.COLOR_GRAY2BGR)
    
    mask = np.ones(target_img_8u.shape[:2], dtype=np.uint8) * 255
    if hide_bg == 1:
        mask = np.zeros(target_img_8u.shape[:2], dtype=np.uint8)

    for box in DISPERSIONS:
        tx1, ty1, tx2, ty2, ux, uy, length = get_true_endpoints(box)
        if length == 0: continue
        
        start_nm, thickness = box['start_nm'], box['thickness']
        vx, vy = -uy, ux
        
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
    global target_img, target_img_8u
    
    target_img = select_image("Select RAW Target Image")
    if target_img is None: return

    # Create the normalized 8-bit copy exactly once at startup to save processing time
    if target_img.dtype == np.uint16:
        target_img_8u = cv2.normalize(target_img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
    else:
        target_img_8u = target_img.copy()

    # Apply Aspect Ratio Fix to Main UI Window
    h, w = target_img.shape[:2]
    aspect_ratio = h / w 
    
    display_width = 1200
    display_height = int(display_width * aspect_ratio)

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, display_width, display_height)
    
    cv2.createTrackbar("Overlays", WINDOW_NAME, 1, 1, update_view)
    cv2.createTrackbar("Hide BG", WINDOW_NAME, 0, 1, update_view)
    cv2.createTrackbar("Min(nm)", WINDOW_NAME, MIN_WAVE_LIMIT, MAX_WAVE_LIMIT, update_view)
    cv2.createTrackbar("Max(nm)", WINDOW_NAME, MAX_WAVE_LIMIT, MAX_WAVE_LIMIT, update_view)

    cv2.setMouseCallback(WINDOW_NAME, on_mouse_click)

    update_view()
    
    print("--- HSIS Viewer Active ---")
    print("- LEFT CLICK near a blue line to see the spectral graph.")
    print("- PRESS 'R' to generate the Visual Datacube Grid.")
    print("- PRESS 'ESC' to exit.")
    
    while True:
        key = cv2.waitKey(10)
        if key == 27: 
            break
        elif key == ord('r') or key == ord('R'):
            reconstruct_grid()
            
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
