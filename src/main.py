"""Main application entry point."""
import logging
import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.uac_helper import is_admin, request_admin_elevation
from src.ui.app_window import MainWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


def main():
    # If not running as admin and no bypass flag, request elevation
    if not is_admin() and "--no-uac" not in sys.argv:
        logger.info("Administrative privileges required to modify network settings. Requesting UAC...")
        if request_admin_elevation():
            sys.exit(0)
        else:
            logger.warning("UAC elevation was declined or failed. Starting in limited mode...")

    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
