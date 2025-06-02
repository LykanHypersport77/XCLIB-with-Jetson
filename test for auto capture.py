import ctypes, time, datetime, os, sys

DLL_NAME = "xclibw64" if sys.maxsize > 2**32 else "xclibw32"
xclib = ctypes.WinDLL(r"C:\Program Files\EPIX\XCLIB\lib\xclibw64.dll")          # stdcall exports

UNIT, CHANNEL, SHOTS = 0, 1, 10

# Helper because WinDLL uses stdcall; we rarely need to set argtypes,
# but it doesn't hurt to define the ones we call frequently.
xclib.pxd_PIXCIopen.argtypes   = [ctypes.c_char_p]*3
xclib.pxd_PIXCIopen.restype    = ctypes.c_int
xclib.pxd_imageZdim.argtypes   = [ctypes.c_int, ctypes.c_int]
xclib.pxd_goSnap.argtypes      = [ctypes.c_int, ctypes.c_int, ctypes.c_int]
xclib.pxd_saveTiff.argtypes    = [
    ctypes.c_int, ctypes.c_char_p,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, ctypes.c_void_p
]

# 1  Open the board – empty strings mean “use defaults”.
if xclib.pxd_PIXCIopen(b"", b"", b"") < 0:
    xclib.pxd_mesgFault(UNIT)
    raise SystemExit("Could not open PIXCI board")

# 2  One host buffer is plenty for snapshots.
xclib.pxd_imageZdim(UNIT, 1)

# 3  Grab‑and‑save loop.
for _ in range(SHOTS):
    xclib.pxd_goSnap(UNIT, CHANNEL, 0)
    fname = datetime.datetime.now().strftime("capture_%Y%m%d_%H%M%S.tif")
    xclib.pxd_saveTiff(
        UNIT, fname.encode(),
        0, 0, -1, -1,        # full frame
        1,                   # buffer index
        16,                  # 16‑bit
        None
    )
    print("saved", fname)
    time.sleep(1)           # optional pause between frames

xclib.pxd_PIXCIclose()