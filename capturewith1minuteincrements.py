import ctypes
import time
import datetime
import os
import sys
import argparse
"""To run a very fast exposure (e.g., 0.5ms) for bright laser testing: python3 capture.py --exp 0.1"""

# --- Parse Command Line Arguments ---
parser = argparse.ArgumentParser(description="Capture 1-minute chunks of hyperspectral video")
parser.add_argument('--fps', type=int, default=30, help="Frames per second (default: 30)")
parser.add_argument('--exp', type=float, default=0.5, help="Exposure time in ms (default: 0.5)")
parser.add_argument('--chunk_time', type=int, default=60, help="Length of each chunk in seconds (default: 60)")
args = parser.parse_args()

# --- Path to the XCLIB shared library ---
DLL_PATH = "/usr/local/xclib/lib/xclib_aarch64.so"
try:
    xclib = ctypes.CDLL(DLL_PATH)
except OSError:
    raise SystemExit(f"Error: Could not load XCLIB at {DLL_PATH}.")

# --- Constants ---
UNIT, CHANNEL = 0, 1
UNITSMAP = 1  

# --- Define C-types function signatures ---
xclib.pxd_PIXCIopen.argtypes = [ctypes.c_char_p] * 3
xclib.pxd_PIXCIopen.restype = ctypes.c_int
xclib.pxd_imageZdim.argtypes = [ctypes.c_int, ctypes.c_int]
xclib.pxd_saveTiff.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
xclib.pxd_mesgFault.argtypes = [ctypes.c_int]
xclib.pxd_serialWrite.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]

# Sequence Capture bindings
xclib.pxd_goLiveSeq.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
xclib.pxd_goneLive.argtypes = [ctypes.c_int, ctypes.c_int]
xclib.pxd_goneLive.restype = ctypes.c_int


# --- Camera Link Serial Functions ---
def send_raptor_command(unit, hex_list):
    chk_sum = 0
    for b in hex_list:
        chk_sum ^= b
    hex_list.append(chk_sum)
    cmd_bytes = bytes(hex_list)
    return xclib.pxd_serialWrite(unit, 1, cmd_bytes, len(cmd_bytes))

def disable_auto_exposure(unit):
    print("Disabling Auto-Exposure (ALC)...")
    cmd = [0x53, 0x00, 0x03, 0x01, 0x00, 0x00, 0x50]
    send_raptor_command(unit, cmd)
    time.sleep(0.1)

def set_exposure_ms(unit, ms):
    print(f"Setting Raptor exposure to {ms} ms...")
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

def set_framerate_hz(unit, hz):
    """Calculates internal 74.25MHz clock ticks to set specific hardware frame rate"""
    print(f"Setting Raptor frame rate to exactly {hz} FPS...")
    # Math derived from Hawk 1920 Manual (1 count = 13.468ns)
    counts = int((1.0 / hz) / 13.468e-9)
    
    y1 = (counts >> 24) & 0xFF  # MSB
    y2 = (counts >> 16) & 0xFF
    y3 = (counts >> 8) & 0xFF
    y4 = counts & 0xFF          # LSB
    
    registers = [(0xDD, y1), (0xDE, y2), (0xDF, y3), (0xE0, y4)]
    for reg, val in registers:
        send_raptor_command(unit, [0x53, 0x00, 0x03, 0x01, reg, val, 0x50])
        time.sleep(0.05)


# --- Main Execution ---
def main():
    SAVE_DIR = os.path.expanduser("~/Downloads/xclib_chunks")
    os.makedirs(SAVE_DIR, exist_ok=True)
    fmt_path = os.path.join(os.path.expanduser("~/Downloads/xclib"), "Pinhole.fmt")

    print(f"Opening PIXCI board...")
    if xclib.pxd_PIXCIopen(b"", b"", fmt_path.encode()) < 0:
        xclib.pxd_mesgFault(UNIT)
        raise SystemExit("Could not open PIXCI board.")

    # --- Hardware Configuration ---
    disable_auto_exposure(UNIT)
    set_exposure_ms(UNIT, args.exp)
    set_framerate_hz(UNIT, args.fps)

    # Calculate required RAM buffer
    FRAMES_PER_CHUNK = int(args.fps * args.chunk_time) 
    print(f"\nAllocating {FRAMES_PER_CHUNK} frames in Jetson RAM...")
    print(f"(This will consume roughly {FRAMES_PER_CHUNK * 5.7 / 1024:.1f} GB of memory)")
    xclib.pxd_imageZdim(UNIT, FRAMES_PER_CHUNK)

    chunk_count = 0
    
    try:
        while True:
            chunk_count += 1
            # Create a new timestamped folder for this specific 1-minute chunk
            folder_name = f"Chunk_{chunk_count}_{datetime.datetime.now().strftime('%H%M%S')}"
            chunk_dir = os.path.join(SAVE_DIR, folder_name)
            os.makedirs(chunk_dir, exist_ok=True)

            print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] --- Recording Chunk {chunk_count} ---")
            print(f"Capturing for {args.chunk_time} seconds (Do NOT cut power)...")
            
            # Start the hardware-level sequence capture (fills buffers 1 through FRAMES_PER_CHUNK)
            xclib.pxd_goLiveSeq(UNITSMAP, 1, FRAMES_PER_CHUNK, 1, 0, 0)
            
            # Wait autonomously until the RAM buffer is completely full
            while xclib.pxd_goneLive(UNITSMAP, 0):
                time.sleep(0.1)
                
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] RAM Buffer Full. Camera is now BLIND.")
            print(f"Saving {FRAMES_PER_CHUNK} images to NVMe drive. Please wait...")
            
            # Unload the RAM buffer into the physical NVMe drive
            for i in range(1, FRAMES_PER_CHUNK + 1):
                tif_path = os.path.join(chunk_dir, f"frame_{i:04d}.tif")
                # The 'i' here points pxd_saveTiff to the correct frame in the RAM sequence
                ret = xclib.pxd_saveTiff(UNITSMAP, tif_path.encode(), i, 0, 0, -1, -1, 0, 0)
                if ret < 0:
                    print(f"Failed to save frame {i}")

            # Force the OS to flush the cache so data survives a hard power cut
            os.sync() 
            print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Chunk {chunk_count} permanently saved to drive. Safe to cut power.")

    except KeyboardInterrupt:
        print(f"\nSequence manually aborted by user.")
        
    finally:
        xclib.pxd_PIXCIclose()
        print("Camera disconnected and board closed safely.")

if __name__ == "__main__":
    main()