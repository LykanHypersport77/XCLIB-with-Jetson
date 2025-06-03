import ctypes
import time
import datetime
import os
import sys

# Path to the XCLIB shared library
DLL_PATH = "/usr/local/xclib/lib/xclib_aarch64.so"
xclib = ctypes.CDLL(DLL_PATH)

# Constants
UNIT, CHANNEL = 0, 1
UNITSMAP = 1  # match Windows code

# Define function signatures
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

# Save directory
SAVE_DIR = os.path.expanduser("~/Downloads/xclib")
os.makedirs(SAVE_DIR, exist_ok=True)

# Hardcoded .fmt path
fmt_path = os.path.join(SAVE_DIR, "Pinhole.fmt")

# Open the PIXCI board with .fmt settings
if xclib.pxd_PIXCIopen(b"", b"", fmt_path.encode()) < 0:
    xclib.pxd_mesgFault(UNIT)
    raise SystemExit("Could not open PIXCI board with .fmt settings")

# Allocate buffer
xclib.pxd_imageZdim(UNIT, 1)

# Get frame dimensions
xclib.pxd_imageXdim = xclib.pxd_imageXdim
xclib.pxd_imageXdim.restype = ctypes.c_int
xclib.pxd_imageYdim = xclib.pxd_imageYdim
xclib.pxd_imageYdim.restype = ctypes.c_int
xdim = xclib.pxd_imageXdim(UNIT)
ydim = xclib.pxd_imageYdim(UNIT)
print("Frame dimensions:", xdim, "x", ydim)

# Snap and save 5 frames
SHOTS = 5
for i in range(SHOTS):
    snap_status = xclib.pxd_goSnap(UNIT, CHANNEL, 0)
    print(f"Snap {i+1}/{SHOTS} status:", snap_status)
    if snap_status < 0:
        xclib.pxd_mesgFault(UNIT)
        continue

    base_name = datetime.datetime.now().strftime("capture_%Y%m%d_%H%M%S")
    tif_name = f"{base_name}_{i+1}.tif"
    tif_path = os.path.join(SAVE_DIR, tif_name)
    print(f"Saving TIFF {i+1} to:", tif_path)

    ret = xclib.pxd_saveTiff(
        UNITSMAP, tif_path.encode(),
        1, 0, 0, -1, -1,
        0, 0
    )
    print(f"pxd_saveTiff returned for image {i+1}:", ret)
    if ret < 0:
        xclib.pxd_mesgFault(UNITSMAP)
        print(f"Failed to save TIFF {i+1} at {tif_path}")
    else:
        print("Successfully saved:", tif_path)

    time.sleep(1)

# Close the PIXCI board
xclib.pxd_PIXCIclose()
