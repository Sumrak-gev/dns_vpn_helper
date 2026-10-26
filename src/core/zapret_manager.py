"""Manager for Zapret (winws) DPI bypass tool."""
import json
import logging
import os
import subprocess
from typing import Dict, Optional, Tuple

from src.core.path_helper import get_base_dir, get_config_file

logger = logging.getLogger(__name__)


def get_zapret_config_path() -> str:
    return get_config_file("zapret_config.json")


class ZapretManager:
    """Controls the winws.exe DPI bypass daemon."""

    _process: Optional[subprocess.Popen] = None

    @classmethod
    def load_config(cls) -> dict:
        """Loads zapret settings from config file."""
        cfg_path = get_zapret_config_path()
        if os.path.isfile(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading zapret config: {e}")
        return {
            "zapret_dir": "tools/zapret",
            "selected_preset": "general",
            "custom_args": "",
            "presets": {},
        }

    @classmethod
    def save_config(cls, data: dict) -> bool:
        """Saves zapret settings to config file."""
        cfg_path = get_zapret_config_path()
        try:
            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Error saving zapret config: {e}")
            return False

    @classmethod
    def find_winws_binary(cls, directory: Optional[str] = None) -> Optional[str]:
        """
        Searches for winws.exe in the given directory or default configured locations.
        """
        config = cls.load_config()
        base_dir = directory or config.get("zapret_dir", "tools/zapret")

        # Convert to absolute path if relative
        if not os.path.isabs(base_dir):
            base_dir = os.path.join(get_base_dir(), base_dir)

        if not os.path.isdir(base_dir):
            return None

        # Check directly in folder
        direct_path = os.path.join(base_dir, "winws.exe")
        if os.path.isfile(direct_path):
            return direct_path

        # Check subdirectories (common in zapret zip archives: bin/, zapret-winws/)
        for root, _, files in os.walk(base_dir):
            if "winws.exe" in files:
                return os.path.join(root, "winws.exe")

        return None

    @classmethod
    def is_running(cls) -> bool:
        """Checks if winws.exe is currently active."""
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            output = subprocess.check_output(
                ["tasklist.exe", "/FI", "IMAGENAME eq winws.exe", "/NH"],
                text=True,
                errors="ignore",
                startupinfo=startupinfo,
            )
            return "winws.exe" in output
        except Exception as e:
            logger.error(f"Error checking winws process: {e}")
            return False

    @classmethod
    def start(cls, preset_key: str = "general", custom_args: str = "") -> Tuple[bool, str]:
        """
        Launches winws.exe with the specified preset or custom arguments.
        """
        winws_path = cls.find_winws_binary()
        if not winws_path:
            return False, "Исполняемый файл winws.exe не найден. Укажите папку с Zapret в настройках."

        # If already running, stop it first to apply new parameters
        if cls.is_running():
            cls.stop()

        config = cls.load_config()
        presets = config.get("presets", {})

        if preset_key == "custom":
            cmd_args = custom_args or config.get("custom_args", "")
        else:
            preset_info = presets.get(preset_key, {})
            cmd_args = preset_info.get("args", "")

        cmd = [winws_path] + cmd_args.split()

        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            # WinDivert driver must be located next to winws.exe
            working_dir = os.path.dirname(winws_path)

            cls._process = subprocess.Popen(
                cmd,
                cwd=working_dir,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )

            # Update selected preset in config
            config["selected_preset"] = preset_key
            if custom_args:
                config["custom_args"] = custom_args
            cls.save_config(config)

            return True, f"Zapret запущен (режим: {presets.get(preset_key, {}).get('name', preset_key)})"
        except Exception as e:
            logger.error(f"Failed to start winws: {e}")
            return False, f"Ошибка запуска winws.exe: {e}"

    @classmethod
    def stop(cls) -> Tuple[bool, str]:
        """Terminates winws.exe process and frees WinDivert filter."""
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            # Kill winws
            subprocess.run(
                ["taskkill.exe", "/F", "/IM", "winws.exe"],
                capture_output=True,
                startupinfo=startupinfo,
            )

            # Also stop WinDivert driver service if created
            subprocess.run(
                ["sc.exe", "stop", "WinDivert"],
                capture_output=True,
                startupinfo=startupinfo,
            )

            cls._process = None
            return True, "Zapret остановлен"
        except Exception as e:
            logger.error(f"Failed to stop winws: {e}")
            return False, f"Ошибка при остановке Zapret: {e}"
