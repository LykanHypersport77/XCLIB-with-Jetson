import ctypes
import time
import os
import argparse

# --- Parse Command Line Arguments ---
parser = argparse.ArgumentParser(description="Windows Exposure Sweep for Raptor Hawk 1920")
parser.add_argument('--start', type=float, default=0.1, help="Starting exposure in ms (default: 0.1)")
parser.add_argument('--stop', type=float, default=5.0, help="Ending exposure in ms (default: 5.0)")
parser.add_argument('--step', type=float, default=0.1, help="Exposure step increment in ms (default: 0.1)")
args = parser.parse_args()

# --- Path to the Windows XCLIB shared library ---
try:
    if hasattr(os, 'add_dll_directory'):
        if os.path.exists(r"C:\PIXCI"):
            os.add_dll_directory(r"C:\PIXCI")
        elif os.path.exists(r"C:\XCAP"):
            os.add_dll_directory(r"C:\XCAP")
            
    xclib = ctypes.CDLL("XCLIBW64.DLL")
except OSError:
    raise SystemExit("Error: Could not load XCLIBW64.DLL. Ensure EPIX XCAP/XCLIB is installed.")

# --- Constants ---
# Use UNITSMAP (Bitmask 1) for ALL commands to target the first PIXCI board
UNITSMAP = 1  

# --- Define C-types function signatures ---
xclib.pxd_PIXCIopen.argtypes = [ctypes.c_char_p] * 3
xclib.pxd_PIXCIopen.restype = ctypes.c_int
xclib.pxd_imageZdim.argtypes = [ctypes.c_int, ctypes.c_int]
xclib.pxd_goSnap.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
xclib.pxd_doSnap.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
xclib.pxd_saveTiff.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
xclib.pxd_mesgFault.argtypes = [ctypes.c_int]
xclib.pxd_serialWrite.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]

# Serial Configure Binding (Crucial for overriding the generic preset's baud rate)
xclib.pxd_serialConfigure.argtypes = [
    ctypes.c_int, ctypes.c_int, ctypes.c_double, ctypes.c_int, 
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int
]
xclib.pxd_serialConfigure.restype = ctypes.c_int


# --- Camera Link Serial Functions ---
def send_raptor_command(unitmap, hex_list):
    """Calculates XOR checksum and sends hex array over Camera Link Serial."""
    chk_sum = 0
    for b in hex_list:
        chk_sum ^= b
    hex_list.append(chk_sum)
    cmd_bytes = bytes(hex_list)
    return xclib.pxd_serialWrite(unitmap, 1, cmd_bytes, len(cmd_bytes))

def disable_auto_exposure(unitmap):
    print("Disabling Auto-Exposure (ALC)...")
    cmd = [0x53, 0x00, 0x03, 0x01, 0x00, 0x00, 0x50]
    send_raptor_command(unitmap, cmd)
    time.sleep(0.1)

def enable_free_run(unitmap):
    print("Forcing camera to Internal Trigger (Free Run)...")
    cmd = [0x53, 0x00, 0x03, 0x01, 0xF2, 0x00, 0x50]
    send_raptor_command(unitmap, cmd)
    time.sleep(0.1)

def set_exposure_ms(unitmap, ms):
    counts = int((ms * 1e-3) / 13.468e-9)
    y0 = (counts >> 32) & 0xFF 
    y1 = (counts >> 24) & 0xFF
    y2 = (counts >> 16) & 0xFF
    y3 = (counts >> 8) & 0xFF
    y4 = counts & 0xFF          
    registers = [(0xED, y0), (0xEE, y1), (0xEF, y2), (0xF0, y3), (0xF1, y4)]
    
    for reg, val in registers:
        send_raptor_command(unitmap, [0x53, 0x00, 0x03, 0x01, reg, val, 0x50])
        time.sleep(0.05)

# --- Main Execution ---
def main():
    SAVE_DIR = os.path.join(os.getcwd(), "Sweep_Captures")
    os.makedirs(SAVE_DIR, exist_ok=True)
    
    fmt_path = r"C:\Users\pkpq4\Documents\SpectralEnergies\HSIS\Pinhole.fmt"

    print(f"Opening PIXCI board using {fmt_path}...")
    if xclib.pxd_PIXCIopen(b"", b"", fmt_path.encode()) < 0:
        xclib.pxd_mesgFault(UNITSMAP)
        raise SystemExit("Could not open PIXCI board. Ensure XCAP is closed.")

    # --- Hardware Configuration ---
    # FORCE 115200 BAUD: This overrides the generic preset so the Raptor can hear us
    xclib.pxd_serialConfigure(UNITSMAP, 1, ctypes.c_double(115200.0), 8, 0, 0, 0, 0, 0)
    time.sleep(0.1)

    disable_auto_exposure(UNITSMAP)
    enable_free_run(UNITSMAP) 
    xclib.pxd_imageZdim(UNITSMAP, 1) 

    print(f"\n--- Starting Exposure Sweep ---")
    print(f"Start: {args.start} ms | Stop: {args.stop} ms | Step: {args.step} ms\n")
    
    current_exp = args.start
    
    try:
        while current_exp <= (args.stop + 0.001): 
            print(f"Setting exposure to {current_exp:.2f} ms...")
            set_exposure_ms(UNITSMAP, current_exp)
            
            time.sleep(0.1) 
            
            # 1. Snap once to flush the old frame (Wait up to 100 fields)
            xclib.pxd_doSnap(UNITSMAP, 1, 100)
            
            # 2. Snap again to capture the actual image with the new exposure
            snap_status = xclib.pxd_doSnap(UNITSMAP, 1, 100)
            
            if snap_status < 0:
                print(f"Snap error code {snap_status} at {current_exp:.2f} ms")
                xclib.pxd_mesgFault(UNITSMAP)
            else:
                tif_name = f"Sweep_{current_exp:.2f}ms.tif"
                tif_path = os.path.join(SAVE_DIR, tif_name)
                
                ret = xclib.pxd_saveTiff(UNITSMAP, tif_path.encode(), 1, 0, 0, -1, -1, 0, 0)
                if ret < 0:
                    print(f"Failed to save {tif_name}")
                else:
                    print(f"Saved: {tif_name}")
            
            current_exp += args.step

    except KeyboardInterrupt:
        print(f"\nSweep manually aborted by user.")
        
    finally:
        xclib.pxd_PIXCIclose()
        print("\nCamera disconnected and board closed safely.")

if __name__ == "__main__":
    main()
