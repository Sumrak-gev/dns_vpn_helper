"""DNS Profiles Manager."""
import ipaddress
import json
import logging
import os
from typing import Dict, List, Optional

from src.core.path_helper import get_config_file

logger = logging.getLogger(__name__)


def get_default_config_path() -> str:
    return get_config_file("profiles.json")


def is_valid_ipv4(ip_str: str) -> bool:
    """Validate IPv4 address string."""
    try:
        ip = ipaddress.IPv4Address(ip_str.strip())
        return not ip.is_loopback and not ip.is_multicast
    except Exception:
        return False


class ProfilesManager:
    """Handles storage and retrieval of DNS profiles."""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or get_default_config_path()
        self.profiles: List[Dict] = []
        self.load()

    def load(self) -> List[Dict]:
        """Loads profiles from JSON file."""
        if not os.path.isfile(self.config_path):
            logger.warning(f"Config file not found at {self.config_path}, using empty list")
            self.profiles = []
            return self.profiles

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                self.profiles = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read profiles: {e}")
            self.profiles = []
        return self.profiles

    def save(self) -> bool:
        """Saves current profiles to JSON file."""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.profiles, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Failed to save profiles: {e}")
            return False

    def get_all(self) -> List[Dict]:
        """Returns all configured profiles."""
        return self.profiles

    def get_by_id(self, profile_id: str) -> Optional[Dict]:
        """Finds a profile by its ID."""
        for p in self.profiles:
            if p.get("id") == profile_id:
                return p
        return None

    def update_ips(self, profile_id: str, primary: str, secondary: Optional[str] = None) -> bool:
        """Updates IP addresses of an existing profile."""
        profile = self.get_by_id(profile_id)
        if not profile:
            return False
        profile["primary"] = primary.strip()
        if secondary:
            profile["secondary"] = secondary.strip()
        return self.save()

    def add_profile(
        self,
        name: str,
        primary: str,
        secondary: str = "",
        description: str = "",
        can_auto_update: bool = False,
        update_url: str = "",
    ) -> Optional[Dict]:
        """Adds a new DNS profile."""
        if not is_valid_ipv4(primary):
            return None
        if secondary and not is_valid_ipv4(secondary):
            return None

        # Generate unique ID
        import re
        base_id = re.sub(r"[^a-zA-Z0-9_]", "", name.lower().replace(" ", "_")) or "custom"
        profile_id = base_id
        counter = 1
        while self.get_by_id(profile_id):
            profile_id = f"{base_id}_{counter}"
            counter += 1

        new_profile = {
            "id": profile_id,
            "name": name,
            "description": description,
            "primary": primary.strip(),
            "secondary": secondary.strip() if secondary else "",
            "can_auto_update": can_auto_update,
            "update_url": update_url,
        }
        self.profiles.append(new_profile)
        self.save()
        return new_profile

    def delete_profile(self, profile_id: str) -> bool:
        """Deletes a profile by its ID."""
        initial_len = len(self.profiles)
        self.profiles = [p for p in self.profiles if p.get("id") != profile_id]
        if len(self.profiles) < initial_len:
            return self.save()
        return False
