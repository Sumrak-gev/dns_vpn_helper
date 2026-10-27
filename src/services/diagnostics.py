"""Network diagnostics and connectivity testing service."""
import logging
import platform
import socket
import subprocess
import time
from typing import Dict, Optional, Tuple
import requests

from src.core.uac_helper import is_admin

logger = logging.getLogger(__name__)

SERVICES_TO_TEST = [
    ("YouTube", "youtube.com", 443),
    ("Discord", "discord.com", 443),
    ("Telegram", "api.telegram.org", 443),
    ("GitHub", "github.com", 443),
    ("Google", "google.com", 443),
]


class NetworkDiagnostics:
    """Network testing and diagnostics tools."""

    @staticmethod
    def get_external_ip(timeout: int = 4) -> Tuple[bool, str]:
        """Fetches public IP address and ISP/country if available."""
        endpoints = [
            "https://api.ipify.org?format=json",
            "https://ifconfig.me/all.json",
            "https://ipinfo.io/json",
        ]
        for url in endpoints:
            try:
                r = requests.get(url, timeout=timeout)
                if r.status_code == 200:
                    data = r.json()
                    ip = data.get("ip") or data.get("ip_addr")
                    if ip:
                        info = ip
                        org = data.get("org") or data.get("company")
                        country = data.get("country")
                        if country or org:
                            info += f" ({country or ''} {org or ''})".strip()
                        return True, info
            except Exception:
                continue
        return False, "Не удалось определить внешний IP"

    @staticmethod
    def test_single_target(host: str, port: int = 443, timeout: float = 1.5) -> Optional[int]:
        """Measures TCP handshake latency in ms."""
        t0 = time.time()
        try:
            sock = socket.create_connection((host, port), timeout=timeout)
            sock.close()
            return int((time.time() - t0) * 1000)
        except Exception:
            return None

    @classmethod
    def test_all_services(cls) -> Dict[str, Optional[int]]:
        """Tests connectivity to all standard services."""
        results = {}
        for name, host, port in SERVICES_TO_TEST:
            latency = cls.test_single_target(host, port)
            results[name] = latency
        return results

    @staticmethod
    def flush_dns() -> Tuple[bool, str]:
        """Flushes local DNS resolver cache using ipconfig."""
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            res = subprocess.run(
                ["ipconfig.exe", "/flushdns"],
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
            )
            if res.returncode == 0:
                return True, "Кэш DNS успешно очищен (ipconfig /flushdns)"
            return False, res.stderr or "Ошибка очистки кэша DNS"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def get_system_summary() -> dict:
        """Returns environment overview."""
        return {
            "os": f"{platform.system()} {platform.release()} (build {platform.version()})",
            "arch": platform.machine(),
            "admin": is_admin(),
        }
