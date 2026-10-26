"""Path helper to handle both development runs and PyInstaller frozen executable runs."""
import os
import shutil
import sys


def get_base_dir() -> str:
    """Returns base directory: directory containing the .exe if compiled, or project root."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_bundle_resource(relative_path: str) -> str:
    """Returns path to a resource inside PyInstaller bundle or project root."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(get_base_dir(), relative_path)


def get_config_file(filename: str) -> str:
    """
    Returns persistent path for a config file.
    If the file doesn't exist in <base_dir>/config, copies the default from bundle if available.
    """
    config_dir = os.path.join(get_base_dir(), "config")
    os.makedirs(config_dir, exist_ok=True)
    target_path = os.path.join(config_dir, filename)

    if not os.path.isfile(target_path):
        bundled_path = get_bundle_resource(os.path.join("config", filename))
        if os.path.isfile(bundled_path):
            try:
                shutil.copy2(bundled_path, target_path)
            except Exception:
                pass
    return target_path
