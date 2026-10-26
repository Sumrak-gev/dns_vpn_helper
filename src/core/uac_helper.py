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
    Relaunch the current script or executable with elevated (Administrator) privileges.
    Returns True if elevation request was dispatched, False otherwise.
    """
    if is_admin():
        return True

    try:
        if getattr(sys, "frozen", False):
            exe = sys.executable
            params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
            hinstance = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe, params.strip(), None, 1
            )
        else:
            script = os.path.abspath(sys.argv[0])
            params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
            hinstance = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, f'"{script}" {params}'.strip(), None, 1
            )
        return hinstance > 32
    except Exception as e:
        print(f"Failed to elevate privileges: {e}")
        return False
