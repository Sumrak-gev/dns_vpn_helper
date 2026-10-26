"""Helper for checking and requesting Windows Administrator (UAC) privileges."""
import ctypes
import os
import sys


def is_admin() -> bool:
    """Check if the current process has administrative privileges."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def request_admin_elevation() -> bool:
    """
    Relaunch the current script with elevated (Administrator) privileges.
    Returns True if elevation request was dispatched, False otherwise.
    """
    if is_admin():
        return True

    script = os.path.abspath(sys.argv[0])
    params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])

    try:
        # Use ShellExecuteW with "runas" verb
        hinstance = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            f'"{script}" {params}'.strip(),
            None,
            1,  # SW_SHOWNORMAL
        )
        # HINSTANCE > 32 indicates success
        if hinstance > 32:
            return True
        return False
    except Exception as e:
        print(f"Failed to elevate privileges: {e}")
        return False
