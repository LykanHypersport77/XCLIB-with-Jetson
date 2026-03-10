import ctypes
import time
import datetime
import os
import sys
import argparse

# --- Parse Command Line Arguments ---
parser = argparse.ArgumentParser(description="Capture full-res images from Raptor Hawk via EPIX PIXCI")
parser.add_argument('--exp', type=float, default=2.0, help="Exposure time in milliseconds (default: 2.0)")
parser.add_argument('--shots', type=int, default=5, help="Number of frames to capture (default: 5)")
args = parser.parse_args()

# --- Path to the XCLIB shared library ---
DLL_PATH = "/usr/local/xclib/lib/xclib_aarch64.so"
try:
    xclib = ctypes.CDLL(DLL_PATH)
except OSError:
    raise SystemExit(f"Error: Could not load XCLIB at {DLL_PATH}. Ensure drivers are installed.")

# --- Constants ---
UNIT, CHANNEL = 0, 1
UNITSMAP = 1  # match Windows code

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

def disable_auto_exposure(unit):
    """Disables the camera's internal ALC (Auto Light Control) so manual exposure works."""
    print("Disabling Auto-Exposure (ALC)...")
    # Reg 0x00: Bit 1 = 0 disables auto gain (ALC)
    cmd = [0x53, 0x00, 0x03, 0x01, 0x00, 0x00, 0x50]
    send_raptor_command(unit, cmd)
    time.sleep(0.1)

def set_exposure_ms(unit, ms):
    """Converts milliseconds to 74.25MHz clock counts and sends 5-byte exposure command."""
    print(f"Setting Raptor exposure to {ms} ms...")
    
    # 1 count = 13.468 nsecs
    counts = int((ms * 1e-3) / 13.468e-9)
    
    # Split 40-bit value into 5 bytes
    y0 = (counts >> 32) & 0xFF  # MSB
    y1 = (counts >> 24) & 0xFF
    y2 = (counts >> 16) & 0xFF
    y3 = (counts >> 8) & 0xFF
    y4 = counts & 0xFF          # LSB
     
    registers = [
        (0xED, y0),
        (0xEE, y1),
        (0xEF, y2),
        (0xF0, y3),
        (0xF1, y4)
    ]
    
    # Send the 5 commands sequentially
    for reg, val in registers:
        cmd = [0x53, 0x00, 0x03, 0x01, reg, val, 0x50]
        send_raptor_command(unit, cmd)
        time.sleep(0.05) # Give the Raptor micro time to process each byte
        
    print(f"Exposure set successfully.")


# --- Main Execution ---
def main():
    # Save directory
    SAVE_DIR = os.path.expanduser("~/Downloads/xclib")
    os.makedirs(SAVE_DIR, exist_ok=True)

    # Hardcoded .fmt path
    fmt_path = os.path.join(SAVE_DIR, "Pinhole.fmt")

    # Open the PIXCI board
    print(f"Opening PIXCI board with {fmt_path}...")
    if xclib.pxd_PIXCIopen(b"", b"", fmt_path.encode()) < 0:
        xclib.pxd_mesgFault(UNIT)
        raise SystemExit("Could not open PIXCI board. Check if another process is using it.")

    # --- Hardware Configuration ---
    disable_auto_exposure(UNIT)
    set_exposure_ms(UNIT, args.exp)

    # Allocate buffer
    xclib.pxd_imageZdim(UNIT, 1)
 
    # Get frame dimensions
    xclib.pxd_imageXdim.restype = ctypes.c_int
    xclib.pxd_imageYdim.restype = ctypes.c_int
    xdim = xclib.pxd_imageXdim(UNIT)
    ydim = xclib.pxd_imageYdim(UNIT)
    print(f"Frame dimensions: {xdim} x {ydim} (Full Resolution)")

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
            base_name = datetime.datetime.now().strftime(f"capture_{args.exp}ms_%Y%m%d_%H%M%S")
            tif_name = f"{base_name}_{frame_count}.tif"
            tif_path = os.path.join(SAVE_DIR, tif_name)

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

                os.sync()  # Ensure data is flushed to disk before next capture (for abrupt power cuts during reentry)

            # Lower this if you want to capture faster
            time.sleep(1) 

    except KeyboardInterrupt:
        # This catches the Ctrl+C command from the terminal
        print(f"\nCapture manually stopped by user after {frame_count} frames.")
        
    finally:
        # Clean up - This ALWAYS runs, even if you crash or press Ctrl+C
        xclib.pxd_PIXCIclose()
        print("Camera disconnected and board closed safely.")

if __name__ == "__main__":
    main()
