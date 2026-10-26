"""Manager for Happ VPN client integration."""
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_HAPP_PATHS = [
    r"C:\Program Files\FlyFrogLLC\Happ\Happ.exe",
    r"C:\Program Files (x86)\FlyFrogLLC\Happ\Happ.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Happ\Happ.exe"),
]


class HappManager:
    """Manages the Happ VPN client process."""

    @staticmethod
    def find_executable(custom_path: Optional[str] = None) -> Optional[str]:
        """Locates the Happ.exe binary."""
        if custom_path and os.path.isfile(custom_path):
            return custom_path
        for path in DEFAULT_HAPP_PATHS:
            if os.path.isfile(path):
                return path
        return None

    @staticmethod
    def is_running() -> bool:
        """Check if Happ.exe process is currently running."""
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            output = subprocess.check_output(
                ["tasklist.exe", "/FI", "IMAGENAME eq Happ.exe", "/NH"],
                text=True,
                errors="ignore",
                startupinfo=startupinfo,
            )
            return "Happ.exe" in output
        except Exception as e:
            logger.error(f"Error checking Happ process: {e}")
            return False

    @classmethod
    def launch_or_focus(cls, custom_path: Optional[str] = None) -> bool:
        """
        Launches Happ if not running, or brings it to the foreground if possible.
        """
        path = cls.find_executable(custom_path)
        if not path:
            logger.error("Happ executable not found")
            return False

        try:
            # Launch Happ.exe
            subprocess.Popen([path], cwd=os.path.dirname(path))
            return True
        except Exception as e:
            logger.error(f"Failed to start Happ: {e}")
            return False

    @staticmethod
    def stop() -> bool:
        """Gracefully closes or terminates Happ.exe."""
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            subprocess.run(
                ["taskkill.exe", "/F", "/IM", "Happ.exe"],
                capture_output=True,
                startupinfo=startupinfo,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to stop Happ: {e}")
            return False
