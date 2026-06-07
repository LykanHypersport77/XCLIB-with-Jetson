import ctypes
import os
import time
import datetime
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import numpy as np
import argparse

# --- Parse Command Line Arguments ---
parser = argparse.ArgumentParser(description="Jetson Ground Test GUI for Raptor Hawk")
parser.add_argument('--fmt', type=str, default="pinhole.fmt", help="Format file to lock the ROI")
args = parser.parse_args()

# --- Path to XCLIB ---
DLL_PATH = "/usr/local/xclib/lib/xclib_aarch64.so"
try:
    xclib = ctypes.CDLL(DLL_PATH)
except OSError:
    raise SystemExit(f"Error: Could not load {DLL_PATH}.")

# --- Constants & C-Types ---
UNIT, CHANNEL, UNITSMAP = 0, 1, 1

xclib.pxd_PIXCIopen.argtypes = [ctypes.c_char_p] * 3
xclib.pxd_PIXCIopen.restype = ctypes.c_int
xclib.pxd_imageZdim.argtypes = [ctypes.c_int, ctypes.c_int]
xclib.pxd_goSnap.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
xclib.pxd_saveTiff.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
xclib.pxd_mesgFault.argtypes = [ctypes.c_int]
xclib.pxd_serialWrite.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]

# --- Hardware Serial Functions ---
def send_raptor_command(unit, hex_list):
    """Calculates XOR checksum and sends byte array over CameraLink serial."""
    chk_sum = 0
    for b in hex_list:
        chk_sum ^= b
    hex_list.append(chk_sum)
    cmd_bytes = bytes(hex_list)
    xclib.pxd_serialWrite(unit, 1, cmd_bytes, len(cmd_bytes))
    # Note: A robust system would also use pxd_serialRead to confirm an "ACK" from the camera

def enable_auto_exposure(unit):
    print("Enabling Auto-Exposure (ALC)...")
    cmd = [0x53, 0x00, 0x03, 0x01, 0x00, 0x01]
    send_raptor_command(unit, cmd)
    time.sleep(1.0)

# --- GUI Application Class ---
class GroundTestApp:
    def __init__(self, root, save_dir, fmt_path):
        self.root = root
        self.root.title("Raptor Ground Test Viewer")
        self.save_dir = save_dir
        
        # Initialize Hardware
        print(f"Opening PIXCI board with {fmt_path}...")
        if xclib.pxd_PIXCIopen(b"", b"", fmt_path.encode()) < 0:
            messagebox.showerror("Hardware Error", "Could not open PIXCI board. Is XCAP open?")
            self.root.destroy()
            return
            
        xclib.pxd_imageZdim(UNIT, 1)
        
        # --- UI: Top Bar (Capture) ---
        self.top_frame = tk.Frame(self.root, pady=10)
        self.top_frame.pack()
        
        self.snap_btn = tk.Button(self.top_frame, text="📸 SNAP & SAVE", font=("Arial", 16, "bold"), bg="green", fg="white", command=self.snap_image)
        self.snap_btn.pack(side=tk.LEFT, padx=10)
        
        self.status_lbl = tk.Label(self.top_frame, text="Ready", font=("Arial", 12))
        self.status_lbl.pack(side=tk.LEFT, padx=20)

        # --- UI: Hardware Controls ---
        self.ctrl_frame = tk.LabelFrame(self.root, text="Camera Hardware Controls", padx=10, pady=10)
        self.ctrl_frame.pack(fill="x", padx=10)

        # Exposure Slider
        self.exp_var = tk.IntVar(value=10) # Default 10ms
        self.exp_slider = tk.Scale(self.ctrl_frame, from_=1, to=1000, orient="horizontal", label="Exposure Time (ms)", variable=self.exp_var, length=250)
        self.exp_slider.bind("<ButtonRelease-1>", self.update_exposure)
        self.exp_slider.grid(row=0, column=0, padx=10)

        # Digital Gain Slider
        self.dgain_var = tk.IntVar(value=0)
        self.dgain_slider = tk.Scale(self.ctrl_frame, from_=0, to=4095, orient="horizontal", label="Digital Gain (Raw)", variable=self.dgain_var, length=250)
        self.dgain_slider.bind("<ButtonRelease-1>", self.update_digital_gain)
        self.dgain_slider.grid(row=0, column=1, padx=10)

        # On-Chip Gain Slider (Usually a small multiplier or index, e.g., 1x to 10x)
        self.again_var = tk.IntVar(value=1)
        self.again_slider = tk.Scale(self.ctrl_frame, from_=1, to=10, orient="horizontal", label="On-Chip Gain", variable=self.again_var, length=250)
        self.again_slider.bind("<ButtonRelease-1>", self.update_onchip_gain)
        self.again_slider.grid(row=0, column=2, padx=10)

        # --- UI: Image Preview ---
        self.canvas = tk.Label(self.root, text="No Image Captured", bg="black", fg="white", width=100, height=20)
        self.canvas.pack(padx=10, pady=10)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- Hardware Control Callbacks ---
    def update_exposure(self, event=None):
        val_ms = self.exp_var.get()
        print(f"Setting Exposure to: {val_ms}ms")
        
        # Example math: Convert ms to microseconds for the camera register
        val_us = val_ms * 1000
        byte1 = (val_us >> 16) & 0xFF
        byte2 = (val_us >> 8) & 0xFF
        byte3 = val_us & 0xFF
        
        # TODO: Replace 0x53 and 0xXX with the exact Raptor Hawk Exposure Write OpCode
        cmd = [0x53, 0xXX, byte1, byte2, byte3] 
        # send_raptor_command(UNIT, cmd) 

    def update_digital_gain(self, event=None):
        val = self.dgain_var.get()
        print(f"Setting Digital Gain to: {val}")
        
        byte1 = (val >> 8) & 0xFF
        byte2 = val & 0xFF
        
        # TODO: Replace with exact Digital Gain OpCode
        cmd = [0x53, 0xXX, byte1, byte2]
        # send_raptor_command(UNIT, cmd)

    def update_onchip_gain(self, event=None):
        val = self.again_var.get()
        print(f"Setting On-Chip Gain to: {val}")
        
        byte1 = val & 0xFF
        
        # TODO: Replace with exact Analog Gain OpCode
        cmd = [0x53, 0xXX, byte1]
        # send_raptor_command(UNIT, cmd)

    # --- Capture & Rendering ---
    def snap_image(self):
        self.status_lbl.config(text="Capturing...", fg="black")
        self.root.update()

        # 1. Trigger hardware capture
        if xclib.pxd_goSnap(UNIT, CHANNEL, 0) < 0:
            self.status_lbl.config(text="Hardware Snap Error!", fg="red")
            xclib.pxd_mesgFault(UNIT)
            return

        # 2. Save TIFF to disk
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        tif_name = f"ground_test_{timestamp}.tif"
        tif_path = os.path.join(self.save_dir, tif_name)

        if xclib.pxd_saveTiff(UNITSMAP, tif_path.encode(), 1, 0, 0, -1, -1, 0, 0) < 0:
            self.status_lbl.config(text="Save Error!", fg="red")
            return
            
        os.sync() # Flush to disk safely on Jetson/Linux
        
        # 3. Load and display preview
        self.display_image(tif_path)
        self.status_lbl.config(text=f"Saved: {tif_name}", fg="green")

    def display_image(self, filepath):
        try:
            img = Image.open(filepath)
            img_arr = np.array(img, dtype=np.uint16)
            
            # Compress 12-bit down to 8-bit for Tkinter display
            img_arr = (img_arr / 4095.0 * 255).astype(np.uint8)
            img_8bit = Image.fromarray(img_arr)
            
            aspect_ratio = img_8bit.height / img_8bit.width
            new_width = 1000
            new_height = int(new_width * aspect_ratio)
            img_resized = img_8bit.resize((new_width, new_height), Image.Resampling.BILINEAR)

            self.tk_img = ImageTk.PhotoImage(img_resized)
            self.canvas.config(image=self.tk_img, text="", width=new_width, height=new_height)
            
        except Exception as e:
            self.status_lbl.config(text=f"Preview Error: {e}", fg="red")

    def on_close(self):
        print("\nClosing hardware connections...")
        xclib.pxd_PIXCIclose()
        self.root.destroy()
        print("Application closed safely.")

# --- Main Boot Sequence ---
def main():
    SAVE_DIR = os.path.expanduser("~/Downloads/xclib/Ground_Tests")
    os.makedirs(SAVE_DIR, exist_ok=True)
    fmt_path = os.path.join(os.path.expanduser("~/Downloads/xclib"), args.fmt)

    root = tk.Tk()
    app = GroundTestApp(root, SAVE_DIR, fmt_path)
    root.mainloop()

if __name__ == "__main__":
    main()
