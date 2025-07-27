"""
Management platform updater module for OTA updates.
"""

from .package_manager import UpdatePackageManager
from .signature_manager import SignatureManager

__all__ = ['UpdatePackageManager', 'SignatureManager']