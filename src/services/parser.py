"""Website parser for extracting up-to-date DNS addresses (e.g. from Comss.one)."""
import logging
import re
from typing import List, Optional, Tuple
import requests

from src.services.profiles_manager import is_valid_ipv4

logger = logging.getLogger(__name__)

DEFAULT_COMSS_URL = "https://comss.one/dns"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class DNSWebsiteParser:
    """Parses and extracts DNS server IPs from websites."""

    @staticmethod
    def fetch_ips_from_url(url: str, timeout: int = 10) -> Tuple[bool, List[str], str]:
        """
        Fetches web page content and extracts IPv4 addresses.
        Returns: (success, list_of_ips, status_message)
        """
        try:
            headers = {"User-Agent": USER_AGENT}
            response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            if response.status_code != 200:
                return False, [], f"Ошибка сервера: HTTP {response.status_code}"

            html = response.text

            # Look for lines mentioning IP or DNS
            found_ips: List[str] = []
            seen = set()

            # Pattern for IPv4
            ip_pattern = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")

            for line in html.splitlines():
                clean_line = re.sub(r"<[^>]+>", " ", line)
                matches = ip_pattern.findall(clean_line)
                for ip in matches:
                    if is_valid_ipv4(ip) and not ip.startswith(("0.", "127.", "192.168.", "10.", "172.")):
                        if ip not in seen:
                            seen.add(ip)
                            found_ips.append(ip)

            if not found_ips:
                return False, [], "На странице не найдены подходящие публичные IPv4 адреса"

            return True, found_ips, f"Успешно получено {len(found_ips)} адресов с сайта"

        except requests.exceptions.Timeout:
            return False, [], "Превышено время ожидания ответа от сайта (таймаут)"
        except requests.exceptions.RequestException as e:
            return False, [], f"Ошибка сетевого запроса: {e}"
        except Exception as e:
            return False, [], f"Непредвиденная ошибка: {e}"

    @classmethod
    def fetch_comss_dns(cls, url: Optional[str] = None) -> Tuple[bool, List[str], str]:
        """
        Specialized fetcher for Comss.one DNS.
        Returns: (success, [primary, secondary], message)
        """
        target_url = url or DEFAULT_COMSS_URL
        success, ips, msg = cls.fetch_ips_from_url(target_url)
        if not success:
            return False, [], msg

        # In Comss, the first 2 unique IPs are usually Primary and Secondary DNS
        selected = ips[:2]
        return True, selected, f"Получены актуальные DNS Comss: {', '.join(selected)}"
