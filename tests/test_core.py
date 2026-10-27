"""Automated tests for DNS & VPN Helper core modules and UI events."""
import os
import sys
import unittest

# Ensure project root in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.dns_manager import DNSManager, ping_dns_server
from src.core.happ_manager import HappManager
from src.core.zapret_manager import ZapretManager
from src.services.diagnostics import NetworkDiagnostics
from src.services.profiles_manager import ProfilesManager, is_valid_ipv4
from src.ui.components import AnimatedButton, lerp_color


class TestProfilesAndValidation(unittest.TestCase):
    def test_ip_validation(self):
        self.assertTrue(is_valid_ipv4("1.1.1.1"))
        self.assertTrue(is_valid_ipv4("8.8.8.8"))
        self.assertTrue(is_valid_ipv4("94.250.253.55"))
        self.assertFalse(is_valid_ipv4("999.999.999.999"))
        self.assertFalse(is_valid_ipv4("abc"))
        self.assertFalse(is_valid_ipv4(""))

    def test_profiles_manager(self):
        pm = ProfilesManager()
        profiles = pm.get_all()
        self.assertGreater(len(profiles), 0)
        self.assertIsNotNone(pm.get_by_id("comss"))
        self.assertIsNotNone(pm.get_by_id("adguard"))

        # Test adding and deleting a custom profile
        new_p = pm.add_profile("Test DNS Profile", "1.2.3.4", "1.2.3.5", "Unit test profile")
        self.assertIsNotNone(new_p)
        self.assertEqual(new_p["primary"], "1.2.3.4")

        # Delete it
        del_ok = pm.delete_profile(new_p["id"])
        self.assertTrue(del_ok)
        self.assertIsNone(pm.get_by_id(new_p["id"]))


class TestZapretManager(unittest.TestCase):
    def test_zapret_scan(self):
        res = ZapretManager.scan_zapret_files()
        self.assertIn("exists", res)
        self.assertIn("has_winws", res)
        self.assertIn("hostlists", res)

    def test_zapret_config(self):
        cfg = ZapretManager.load_config()
        self.assertIn("presets", cfg)
        self.assertIn("general", cfg["presets"])


class TestNetworkDiagnostics(unittest.TestCase):
    def test_system_summary(self):
        summary = NetworkDiagnostics.get_system_summary()
        self.assertIn("os", summary)
        self.assertIn("arch", summary)

    def test_single_target_ping(self):
        ms = NetworkDiagnostics.test_single_target("google.com", 443, timeout=2.0)
        self.assertIsNotNone(ms)
        self.assertGreater(ms, 0)


class TestDNSManager(unittest.TestCase):
    def test_active_adapter(self):
        adapter = DNSManager.get_active_adapter()
        self.assertIsNotNone(adapter)
        self.assertIn("index", adapter)
        self.assertIn("ipv4_dns", adapter)

    def test_dns_ping(self):
        ms = ping_dns_server("8.8.8.8", timeout=2.0)
        self.assertIsNotNone(ms)
        self.assertGreater(ms, 0)


class TestAnimatedButton(unittest.TestCase):
    def test_command_execution(self):
        import customtkinter as ctk

        app = ctk.CTk()
        clicked = []
        btn = AnimatedButton(app, text="Test", command=lambda: clicked.append("OK"))
        btn.pack()
        app.update()

        # Trigger button release event
        btn._on_enter()
        btn._on_release()

        self.assertEqual(clicked, ["OK"])
        app.destroy()

    def test_lerp_color(self):
        mid = lerp_color("#000000", "#FFFFFF", 0.5)
        self.assertEqual(mid.lower(), "#808080")


if __name__ == "__main__":
    unittest.main()
