import ctypes
import time
import datetime
import os
import sys

# Path to the XCLIB shared library
DLL_PATH = "/usr/local/xclib/lib/xclib_aarch64.so"
xclib = ctypes.CDLL(DLL_PATH)

# Constants
UNIT, CHANNEL, SHOTS = 0, 1, 10

# Define function signatures for XCLIB functions
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

# Print the current working directory for reference
print("Current working directory:", os.getcwd())

# Open the PIXCI board with defaults
if xclib.pxd_PIXCIopen(b"", b"", b"") < 0:
    xclib.pxd_mesgFault(UNIT)
    raise SystemExit("Could not open PIXCI board")

# Allocate one buffer for snapshot
xclib.pxd_imageZdim(UNIT, 1)

# Directory to save TIFF files (absolute path)
SAVE_DIR = os.path.expanduser("~/Downloads/xclib")
os.makedirs(SAVE_DIR, exist_ok=True)

# Loop to capture and save TIFF files
for shot_num in range(SHOTS):
    # Snap a frame
    snap_ret = xclib.pxd_goSnap(UNIT, CHANNEL, 0)
    print(f"Snap {shot_num+1}/{SHOTS} - pxd_goSnap returned:", snap_ret)
    if snap_ret < 0:
        xclib.pxd_mesgFault(UNIT)
        continue  # Skip to next shot

    # Generate a timestamped filename with absolute path
    timestamp = datetime.datetime.now().strftime("capture_%Y%m%d_%H%M%S.tif")
    tif_path = os.path.join(SAVE_DIR, timestamp)
    print("Attempting to save TIFF to:", tif_path)

    # Save the TIFF file
    ret = xclib.pxd_saveTiff(
        UNIT, tif_path.encode(),
        0, 0, -1, -1,       # full frame
        1,                  # buffer index
        16,                 # 16-bit
        None
    )
    print("pxd_saveTiff returned:", ret)
    if ret < 0:
        print(f"Failed to save TIFF at {tif_path}")
        xclib.pxd_mesgFault(UNIT)
    else:
        print("Successfully saved:", tif_path)

    time.sleep(1)  # optional pause between frames

# Close the PIXCI board
xclib.pxd_PIXCIclose()
