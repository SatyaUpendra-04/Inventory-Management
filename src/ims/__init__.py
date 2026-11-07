"""Inventory Management System: drone and survey equipment, pilots, projects and maintenance."""

from importlib.metadata import PackageNotFoundError, version

APP_NAME = "Inventory Management"
APP_ID = "IMS"

try:
    __version__ = version("ims")
except PackageNotFoundError:  # running from a source tree without installation
    __version__ = "0.0.0+unknown"
