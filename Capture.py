import ctypes
import time
import datetime
import os
import argparse

# --- Parse Command Line Arguments ---
parser = argparse.ArgumentParser(description="Auto-Exposure 12-bit Middle Crop Capture for Raptor Hawk on Jetson")
parser.add_argument('--fmt', type=str, default="MiddleThird_12bit.fmt", help="Name of your 12-bit cropped format file")
args = parser.parse_args()

# --- Path to the XCLIB shared library for Jetson (ARM64) ---
DLL_PATH = "/usr/local/xclib/lib/xclib_aarch64.so"
try:
    xclib = ctypes.CDLL(DLL_PATH)
except OSError:
    raise SystemExit(f"Error: Could not load XCLIB at {DLL_PATH}. Ensure EPIX drivers are installed for aarch64.")

# --- Constants ---
UNIT, CHANNEL = 0, 1
UNITSMAP = 1  

# --- Define C-types function signatures ---
xclib.pxd_PIXCIopen.argtypes = [ctypes.c_char_p] * 3
xclib.pxd_PIXCIopen.restype = ctypes.c_int

xclib.pxd_imageZdim.argtypes = [ctypes.c_int, ctypes.c_int]

xclib.pxd_goSnap.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]

xclib.pxd_saveTiff.argtypes = [
    ctypes.c_int, ctypes.c_char_p,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, ctypes.c_void_p
]

xclib.pxd_mesgFault.argtypes = [ctypes.c_int]

# Serial Write Binding for Camera Link
xclib.pxd_serialWrite.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
xclib.pxd_serialWrite.restype = ctypes.c_int

# --- Camera Link Serial Functions ---
def send_raptor_command(unit, hex_list):
    """Calculates XOR checksum and sends hex array over Camera Link Serial."""
    chk_sum = 0
    for b in hex_list:
        chk_sum ^= b
    
    hex_list.append(chk_sum)
    cmd_bytes = bytes(hex_list)
    
    # Port 1 is standard for EPIX CL Base serial communication
    ret = xclib.pxd_serialWrite(unit, 1, cmd_bytes, len(cmd_bytes))
    return ret

def enable_auto_exposure(unit):
    """Enables the camera's internal ALC (Auto Light Control)."""
    print("Enabling Auto-Exposure (ALC) over Camera Link...")
    # Reg 0x00: Bit 1 = 1 enables auto gain/exposure (ALC)
    cmd = [0x53, 0x00, 0x03, 0x01, 0x00, 0x01]
    send_raptor_command(unit, cmd)
    
    # Give the sensor 1 second to analyze ambient light and adjust the clock
    time.sleep(1.0)


# --- Main Execution ---
def main():
    # Setup Jetson save directory
    SAVE_DIR = os.path.expanduser("~/Downloads/xclib")
    os.makedirs(SAVE_DIR, exist_ok=True)

    fmt_path = os.path.join(SAVE_DIR, args.fmt)

    # Open the PIXCI board
    print(f"Opening PIXCI board with {fmt_path}...")
    if xclib.pxd_PIXCIopen(b"", b"", fmt_path.encode()) < 0:
        xclib.pxd_mesgFault(UNIT)
        raise SystemExit(f"Could not open PIXCI board using {fmt_path}. Check if the file exists and XCAP is closed.")

    # --- Hardware Configuration ---
    # Turn on Auto Exposure
    enable_auto_exposure(UNIT)

    # Allocate a single frame buffer
    xclib.pxd_imageZdim(UNIT, 1)
 
    # Get frame dimensions to verify the crop worked
    xclib.pxd_imageXdim.restype = ctypes.c_int
    xclib.pxd_imageYdim.restype = ctypes.c_int
    xdim = xclib.pxd_imageXdim(UNIT)
    ydim = xclib.pxd_imageYdim(UNIT)
    
    print(f"Verified Frame Dimensions: {xdim} x {ydim} (12-bit Hardware Crop)")

    # --- INFINITE CAPTURE LOOP ---
    print("\nStarting infinite capture. Press Ctrl+C to stop...")
    frame_count = 0
    
    try:
        while True:
            snap_status = xclib.pxd_goSnap(UNIT, CHANNEL, 0)
            if snap_status < 0:
                print(f"Snap error on frame {frame_count+1}")
                xclib.pxd_mesgFault(UNIT)
                continue

            frame_count += 1
            # Note: Removed the hardcoded exposure from the filename since it's auto now
            base_name = datetime.datetime.now().strftime("capture_auto_%Y%m%d_%H%M%S")
            tif_name = f"{base_name}_{frame_count}.tif"
            tif_path = os.path.join(SAVE_DIR, tif_name)

            # Save the 12-bit cropped TIFF
            ret = xclib.pxd_saveTiff(
                UNITSMAP, tif_path.encode(),
                1, 0, 0, -1, -1,
                0, 0
            )
            
            if ret < 0:
                xclib.pxd_mesgFault(UNITSMAP)
                print(f"Failed to save TIFF {frame_count} at {tif_path}")
            else:
                print(f"Successfully saved frame {frame_count}: {tif_name}")

                # Ensure data is flushed to disk before next capture (crucial for sudden power cuts)
                os.sync() 

            # Lower this if you want to capture faster (e.g., time.sleep(0.1))
            time.sleep(0.1) 

    except KeyboardInterrupt:
        # This catches the Ctrl+C command from the terminal safely
        print(f"\nCapture manually stopped by user after {frame_count} frames.")
        
    finally:
        # Clean up - This ALWAYS runs, even if the script crashes or you press Ctrl+C
        xclib.pxd_PIXCIclose()
        print("Camera disconnected and EPIX board closed safely.")

if __name__ == "__main__":
    main()
