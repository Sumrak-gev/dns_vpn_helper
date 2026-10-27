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
    def is_service_running() -> bool:
        """Checks if HappService Windows Service is running."""
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            out = subprocess.check_output(
                ["sc.exe", "query", "HappService"],
                text=True,
                errors="ignore",
                startupinfo=startupinfo,
            )
            return "STATE" in out and "RUNNING" in out
        except Exception:
            return False

    @staticmethod
    def restart_service() -> tuple[bool, str]:
        """Restarts HappService Windows Service."""
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            subprocess.run(["net.exe", "stop", "HappService"], capture_output=True, startupinfo=startupinfo)
            res = subprocess.run(["net.exe", "start", "HappService"], capture_output=True, text=True, startupinfo=startupinfo)
            if res.returncode == 0:
                return True, "Служба HappService успешно перезапущена"
            return False, res.stderr or "Не удалось запустить HappService"
        except Exception as e:
            return False, str(e)

    @classmethod
    def get_process_info(cls) -> Optional[dict]:
        """Returns details about running Happ process (PID, memory)."""
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            out = subprocess.check_output(
                ["tasklist.exe", "/FI", "IMAGENAME eq Happ.exe", "/FO", "CSV", "/NH"],
                text=True,
                errors="ignore",
                startupinfo=startupinfo,
            )
            for line in out.strip().splitlines():
                parts = [p.strip(' "') for p in line.split('","')]
                if len(parts) >= 5 and "Happ.exe" in parts[0]:
                    return {
                        "name": parts[0],
                        "pid": parts[1],
                        "session": parts[2],
                        "mem": parts[4],
                    }
        except Exception:
            pass
        return None
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
