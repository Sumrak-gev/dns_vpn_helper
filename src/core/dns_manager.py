"""DNS Manager for Windows network interfaces."""
import json
import logging
import socket
import subprocess
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def ping_dns_server(ip: str, port: int = 53, timeout: float = 1.0) -> Optional[int]:
    """Measures DNS server round-trip latency in milliseconds via UDP query."""
    if not ip or not ip.strip():
        return None
    # Minimal DNS request for 'com'
    query = b"\xaa\xbb\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x03www\x06google\x03com\x00\x00\x01\x00\x01"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    t0 = time.time()
    try:
        sock.sendto(query, (ip.strip(), port))
        sock.recvfrom(512)
        return int((time.time() - t0) * 1000)
    except Exception:
        return None
    finally:
        sock.close()


class DNSManager:
    """Manages DNS configuration on Windows network adapters."""

    @staticmethod
    def _run_ps(command: str) -> Tuple[int, str, str]:
        """Execute a PowerShell command with UTF-8 encoding and return (code, stdout, stderr)."""
        full_command = f"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; {command}"
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

            res = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", full_command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=startupinfo,
            )
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        except Exception as e:
            logger.error(f"PowerShell execution failed: {e}")
            return -1, "", str(e)

    @classmethod
    def get_active_adapter(cls) -> Optional[Dict]:
        """
        Detects the active network adapter with the default route (gateway).
        Returns dict with keys: index, alias, description, ipv4_dns, is_dhcp.
        """
        ps_cmd = (
            "Get-NetRoute -DestinationPrefix '0.0.0.0/0' | "
            "Sort-Object RouteMetric | "
            "Select-Object -First 1 | "
            "ForEach-Object { "
            "  $idx = $_.InterfaceIndex; "
            "  $adapter = Get-NetAdapter -InterfaceIndex $idx -ErrorAction SilentlyContinue; "
            "  [PSCustomObject]@{ "
            "    InterfaceIndex = $idx; "
            "    InterfaceAlias = $_.InterfaceAlias; "
            "    Description = if ($adapter) { $adapter.InterfaceDescription } else { 'Network Adapter' } "
            "  } "
            "} | ConvertTo-Json"
        )
        code, out, err = cls._run_ps(ps_cmd)
        if code != 0 or not out:
            logger.warning(f"Failed to find default route: {err}")
            return None

        try:
            route_data = json.loads(out)
            idx = int(route_data["InterfaceIndex"])
            desc = route_data.get("Description") or "Сетевой адаптер"
            alias = route_data.get("InterfaceAlias") or f"Адаптер #{idx}"

            # Get DNS info
            dns_info = cls.get_adapter_dns(idx)

            return {
                "index": idx,
                "alias": alias,
                "description": desc,
                "ipv4_dns": dns_info.get("servers", []),
                "is_dhcp": dns_info.get("is_dhcp", True),
            }
        except Exception as e:
            logger.error(f"Error parsing adapter info: {e}")
            return None

    @classmethod
    def get_adapter_dns(cls, interface_index: int) -> Dict:
        """Get current IPv4 DNS servers for a given interface index."""
        ps_cmd = (
            f"Get-DnsClientServerAddress -InterfaceIndex {interface_index} -AddressFamily IPv4 | "
            "Select-Object InterfaceIndex, ServerAddresses | "
            "ConvertTo-Json"
        )
        code, out, _ = cls._run_ps(ps_cmd)
        servers = []
        if code == 0 and out:
            try:
                data = json.loads(out)
                raw_servers = data.get("ServerAddresses")
                if isinstance(raw_servers, list):
                    servers = [s.strip() for s in raw_servers if s and s.strip()]
                elif isinstance(raw_servers, str) and raw_servers.strip():
                    servers = [raw_servers.strip()]
            except Exception:
                pass

        # Check if interface uses DHCP for DNS
        # Netsh or Get-DnsClient can tell us if DNS is statically configured
        ps_dhcp_check = f"(Get-DnsClient -InterfaceIndex {interface_index}).ConnectionSpecificSuffix"
        # In PowerShell, if ServerAddresses is empty or auto-assigned, we can verify via netsh
        # If servers list is non-empty, we consider it configured.
        return {
            "servers": servers,
            "is_dhcp": len(servers) == 0,
        }

    @classmethod
    def set_dns(cls, servers: List[str], interface_index: Optional[int] = None) -> Tuple[bool, str]:
        """
        Sets static IPv4 DNS servers on the specified adapter (or active adapter if None).
        Clears the local DNS resolver cache.
        """
        if interface_index is None:
            active = cls.get_active_adapter()
            if not active:
                return False, "Активный сетевой адаптер не найден"
            interface_index = active["index"]

        valid_ips = [s.strip() for s in servers if s and s.strip()]
        if not valid_ips:
            return False, "Список DNS адресов пуст"

        # Format as PowerShell array: @('1.1.1.1', '1.0.0.1')
        ips_ps = "@(" + ", ".join([f"'{ip}'" for ip in valid_ips]) + ")"
        ps_cmd = f"Set-DnsClientServerAddress -InterfaceIndex {interface_index} -ServerAddresses {ips_ps} -PassThru"

        code, out, err = cls._run_ps(ps_cmd)
        if code != 0:
            msg = err or "Ошибка при применении DNS (требуются права администратора)"
            return False, msg

        # Flush DNS cache
        cls.flush_dns()
        return True, f"Установлен DNS: {', '.join(valid_ips)}"

    @classmethod
    def reset_to_dhcp(cls, interface_index: Optional[int] = None) -> Tuple[bool, str]:
        """
        Resets DNS configuration on the adapter to DHCP (automatic).
        Clears the local DNS resolver cache.
        """
        if interface_index is None:
            active = cls.get_active_adapter()
            if not active:
                return False, "Активный сетевой адаптер не найден"
            interface_index = active["index"]

        ps_cmd = f"Set-DnsClientServerAddress -InterfaceIndex {interface_index} -ResetServerAddresses"
        code, out, err = cls._run_ps(ps_cmd)
        if code != 0:
            msg = err or "Ошибка при сбросе DNS (требуются права администратора)"
            return False, msg

        cls.flush_dns()
        return True, "DNS успешно переключен на автоматический (DHCP)"

    @classmethod
    def flush_dns(cls) -> bool:
        """Flushes the Windows DNS client cache."""
        code, _, _ = cls._run_ps("Clear-DnsClientCache")
        return code == 0
