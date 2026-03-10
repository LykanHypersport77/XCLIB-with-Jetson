import ctypes
import time
import datetime
import os
import argparse

# --- Parse Command Line Arguments ---
parser = argparse.ArgumentParser(description="Windows Exposure Sweep for Raptor Hawk 1920")
parser.add_argument('--start', type=float, default=0.1, help="Starting exposure in ms (default: 0.1)")
parser.add_argument('--stop', type=float, default=5.0, help="Ending exposure in ms (default: 5.0)")
parser.add_argument('--step', type=float, default=0.1, help="Exposure step increment in ms (default: 0.1)")
parser.add_argument('--fmt', type=str, default="Pinhole.fmt", help="Path to your .fmt file")
args = parser.parse_args()

# --- Path to the Windows XCLIB shared library ---
try:
    # Loads the 64-bit Windows EPIX library (Must have EPIX drivers installed on this PC)
    xclib = ctypes.CDLL("XCLIBW64.DLL")
except OSError:
    raise SystemExit("Error: Could not load XCLIBW64.DLL. Ensure EPIX XCAP/XCLIB is installed and you are using 64-bit Python.")

# --- Constants ---
UNIT, CHANNEL = 0, 1
UNITSMAP = 1  

# --- Define C-types function signatures ---
xclib.pxd_PIXCIopen.argtypes = [ctypes.c_char_p] * 3
xclib.pxd_PIXCIopen.restype = ctypes.c_int
xclib.pxd_imageZdim.argtypes = [ctypes.c_int, ctypes.c_int]
xclib.pxd_goSnap.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
xclib.pxd_saveTiff.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
xclib.pxd_mesgFault.argtypes = [ctypes.c_int]
xclib.pxd_serialWrite.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]

# --- Camera Link Serial Functions ---
def send_raptor_command(unit, hex_list):
    """Calculates XOR checksum and sends hex array over Camera Link Serial."""
    chk_sum = 0
    for b in hex_list:
        chk_sum ^= b
    hex_list.append(chk_sum)
    cmd_bytes = bytes(hex_list)
    return xclib.pxd_serialWrite(unit, 1, cmd_bytes, len(cmd_bytes))

def disable_auto_exposure(unit):
    """Disables the camera's internal ALC (Auto Light Control)."""
    print("Disabling Auto-Exposure (ALC)...")
    cmd = [0x53, 0x00, 0x03, 0x01, 0x00, 0x00, 0x50]
    send_raptor_command(unit, cmd)
    time.sleep(0.1)

def set_exposure_ms(unit, ms):
    """Converts milliseconds to hardware clock counts and sends via Serial."""
    # 1 count = 13.468 nsecs
    counts = int((ms * 1e-3) / 13.468e-9)
    y0 = (counts >> 32) & 0xFF 
    y1 = (counts >> 24) & 0xFF
    y2 = (counts >> 16) & 0xFF
    y3 = (counts >> 8) & 0xFF
    y4 = counts & 0xFF          
    registers = [(0xED, y0), (0xEE, y1), (0xEF, y2), (0xF0, y3), (0xF1, y4)]
    
    for reg, val in registers:
        send_raptor_command(unit, [0x53, 0x00, 0x03, 0x01, reg, val, 0x50])
        time.sleep(0.05)

# --- Main Execution ---
def main():
    # Setup Windows save directory in the current working folder
    SAVE_DIR = os.path.join(os.getcwd(), "Sweep_Captures")
    os.makedirs(SAVE_DIR, exist_ok=True)
    
    fmt_path = args.fmt

    print(f"Opening PIXCI board using {fmt_path}...")
    if xclib.pxd_PIXCIopen(b"", b"", fmt_path.encode()) < 0:
        xclib.pxd_mesgFault(UNIT)
        raise SystemExit("Could not open PIXCI board. Ensure XCAP is closed.")

    # --- Hardware Configuration ---
    disable_auto_exposure(UNIT)
    xclib.pxd_imageZdim(UNIT, 1) # Only need 1 buffer for single snaps

    print(f"\n--- Starting Exposure Sweep ---")
    print(f"Start: {args.start} ms | Stop: {args.stop} ms | Step: {args.step} ms\n")
    
    current_exp = args.start
    
    try:
        while current_exp <= (args.stop + 0.001): # +0.001 handles float rounding errors
            print(f"Setting exposure to {current_exp:.2f} ms...")
            set_exposure_ms(UNIT, current_exp)
            
            # Give the sensor a tiny fraction of a second to apply the new exposure
            time.sleep(0.1) 
            
            # Snap the image
            snap_status = xclib.pxd_goSnap(UNIT, CHANNEL, 0)
            if snap_status < 0:
                print(f"Snap error at {current_exp:.2f} ms")
                xclib.pxd_mesgFault(UNIT)
            else:
                # Save the image with the exact exposure time in the filename
                tif_name = f"Sweep_{current_exp:.2f}ms.tif"
                tif_path = os.path.join(SAVE_DIR, tif_name)
                
                ret = xclib.pxd_saveTiff(UNITSMAP, tif_path.encode(), 1, 0, 0, -1, -1, 0, 0)
                if ret < 0:
                    print(f"Failed to save {tif_name}")
                else:
                    print(f"Saved: {tif_name}")
            
            # Increment exposure for the next loop
            current_exp += args.step

    except KeyboardInterrupt:
        print(f"\nSweep manually aborted by user.")
        
    finally:
        xclib.pxd_PIXCIclose()
        print("\nCamera disconnected and board closed safely.")

if __name__ == "__main__":
    main()