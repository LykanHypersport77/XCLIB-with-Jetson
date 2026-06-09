import ctypes
import time
import datetime
import os

# ==========================================================
# --- FLIGHT HARDWARE SETTINGS (EDIT THESE BEFORE LAUNCH) ---
# ==========================================================
FORMAT_FILE = "pinhole.fmt"
EXPOSURE_MS = 40      # Exposure time in milliseconds
DIGITAL_GAIN = 4608   # Raw digital gain (Min 256 = 1x Gain)
ANALOG_GAIN = 180      # On-chip analog gain (0-240 counts)
# ==========================================================

DLL_PATH = "/usr/local/xclib/lib/xclib_aarch64.so"
try:
    xclib = ctypes.CDLL(DLL_PATH)
except OSError:
    raise SystemExit(f"Error: Could not load XCLIB at {DLL_PATH}. Ensure EPIX drivers are installed for aarch64.")

UNIT, CHANNEL, UNITSMAP = 0, 1, 1

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
xclib.pxd_serialWrite.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
xclib.pxd_serialWrite.restype = ctypes.c_int

def send_raptor_command(unit, hex_list):
    """Calculates XOR checksum and sends hex array over Camera Link Serial."""
    chk_sum = 0
    for b in hex_list:
        chk_sum ^= b
    
    hex_list.append(chk_sum)
    cmd_bytes = bytes(hex_list)
    xclib.pxd_serialWrite(unit, 1, cmd_bytes, len(cmd_bytes))
    time.sleep(0.05)

def lock_hardware_settings(unit, exp_ms, dgain, again):
    """Sends exact, hardcoded exposure and gain settings to the Raptor."""
    print(f"Locking Hardware: Exposure={exp_ms}ms, Digital Gain={dgain}, Analog Gain={again}")
    
    # 1. Disable Auto Exposure (ALC) - FORCE MANUAL MODE
    send_raptor_command(unit, [0x53, 0x00, 0x03, 0x01, 0x00, 0x00, 0x50])

    # 2. Set Exposure (40-bit across 5 bytes)
    exp_counts = int(exp_ms * 74250)
    y0 = (exp_counts >> 32) & 0xFF
    y1 = (exp_counts >> 24) & 0xFF
    y2 = (exp_counts >> 16) & 0xFF
    y3 = (exp_counts >> 8) & 0xFF
    y4 = exp_counts & 0xFF

    send_raptor_command(unit, [0x53, 0x00, 0x03, 0x01, 0xED, y0, 0x50])
    send_raptor_command(unit, [0x53, 0x00, 0x03, 0x01, 0xEE, y1, 0x50])
    send_raptor_command(unit, [0x53, 0x00, 0x03, 0x01, 0xEF, y2, 0x50])
    send_raptor_command(unit, [0x53, 0x00, 0x03, 0x01, 0xF0, y3, 0x50])
    send_raptor_command(unit, [0x53, 0x00, 0x03, 0x01, 0xF1, y4, 0x50]) 
    
    # 3. Set Digital Gain (16-bit across 2 bytes)
    d1 = (dgain >> 8) & 0xFF
    d2 = dgain & 0xFF
    
    send_raptor_command(unit, [0x53, 0x00, 0x03, 0x01, 0xC6, d1, 0x50])
    send_raptor_command(unit, [0x53, 0x00, 0x03, 0x01, 0xC7, d2, 0x50]) 
    
    # 4. Set Analog Gain (Unlock Sequence + Set)
    a1 = again & 0xFF
    
    send_raptor_command(unit, [0x53, 0x00, 0x03, 0x01, 0xE5, 0x35, 0x50]) 
    send_raptor_command(unit, [0x53, 0x00, 0x03, 0x01, 0xE6, 0x14, 0x50]) 
    send_raptor_command(unit, [0x53, 0x00, 0x03, 0x01, 0xE7, a1, 0x50])
    
    print("Hardware locked. Ready for capture.")

def main():
    SAVE_DIR = os.path.expanduser("~/Downloads/xclib")
    os.makedirs(SAVE_DIR, exist_ok=True)
    fmt_path = os.path.join(SAVE_DIR, FORMAT_FILE)

    print(f"Opening PIXCI board with {fmt_path}...")
    if xclib.pxd_PIXCIopen(b"", b"", fmt_path.encode()) < 0:
        xclib.pxd_mesgFault(UNIT)
        raise SystemExit(f"Could not open PIXCI board. Check if {FORMAT_FILE} exists and XCAP is closed.")

    lock_hardware_settings(UNIT, EXPOSURE_MS, DIGITAL_GAIN, ANALOG_GAIN)
    xclib.pxd_imageZdim(UNIT, 1)

    print("\nStarting INFINITE FLIGHT CAPTURE. Press Ctrl+C to stop...")
    frame_count = 0
    
    try:
        while True:
            snap_status = xclib.pxd_goSnap(UNIT, CHANNEL, 0)
            if snap_status < 0:
                print(f"Snap error on frame {frame_count+1}")
                xclib.pxd_mesgFault(UNIT)
                continue

            frame_count += 1
            base_name = datetime.datetime.now().strftime(f"capture_{EXPOSURE_MS}ms_%Y%m%d_%H%M%S")
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
                print(f"Saved: {tif_name}")
                os.sync() 

            time.sleep(0.1) 

    except KeyboardInterrupt:
        print(f"\nCapture safely terminated after {frame_count} frames.")
        
    finally:
        xclib.pxd_PIXCIclose()
        print("Hardware disengaged.")

if __name__ == "__main__":
    main()
