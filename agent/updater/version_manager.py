"""
Version management module for agent OTA updates.
Handles version control mechanisms and version comparison logic.
"""

import re
import json
import os
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class VersionType(Enum):
    """Version type enumeration."""
    MAJOR = "major"
    MINOR = "minor"
    PATCH = "patch"
    PRERELEASE = "prerelease"


@dataclass
class Version:
    """Version information structure."""
    major: int
    minor: int
    patch: int
    prerelease: Optional[str] = None
    build_metadata: Optional[str] = None
    
    def __str__(self) -> str:
        """String representation of version."""
        version_str = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            version_str += f"-{self.prerelease}"
        if self.build_metadata:
            version_str += f"+{self.build_metadata}"
        return version_str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert version to dictionary."""
        return {
            "major": self.major,
            "minor": self.minor,
            "patch": self.patch,
            "prerelease": self.prerelease,
            "build_metadata": self.build_metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Version':
        """Create version from dictionary."""
        return cls(
            major=data["major"],
            minor=data["minor"],
            patch=data["patch"],
            prerelease=data.get("prerelease"),
            build_metadata=data.get("build_metadata")
        )


class VersionManager:
    """
    Version manager for handling agent version control and comparison.
    Implements semantic versioning (SemVer) specification.
    """
    
    VERSION_PATTERN = re.compile(
        r'^(?P<major>0|[1-9]\d*)'
        r'\.(?P<minor>0|[1-9]\d*)'
        r'\.(?P<patch>0|[1-9]\d*)'
        r'(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)'
        r'(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?'
        r'(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'
    )
    
    def __init__(self, version_file_path: str = "version.json"):
        """
        Initialize version manager.
        
        Args:
            version_file_path: Path to version file
        """
        self.version_file_path = version_file_path
        self._current_version: Optional[Version] = None
        
    def parse_version(self, version_string: str) -> Version:
        """
        Parse version string into Version object.
        
        Args:
            version_string: Version string in semantic versioning format
            
        Returns:
            Version object
            
        Raises:
            ValueError: If version string is invalid
        """
        match = self.VERSION_PATTERN.match(version_string.strip())
        if not match:
            raise ValueError(f"Invalid version string: {version_string}")
        
        groups = match.groupdict()
        return Version(
            major=int(groups['major']),
            minor=int(groups['minor']),
            patch=int(groups['patch']),
            prerelease=groups.get('prerelease'),
            build_metadata=groups.get('buildmetadata')
        )
    
    def compare_versions(self, version1: Version, version2: Version) -> int:
        """
        Compare two versions according to semantic versioning rules.
        
        Args:
            version1: First version to compare
            version2: Second version to compare
            
        Returns:
            -1 if version1 < version2
             0 if version1 == version2
             1 if version1 > version2
        """
        # Compare major, minor, patch
        for attr in ['major', 'minor', 'patch']:
            v1_val = getattr(version1, attr)
            v2_val = getattr(version2, attr)
            if v1_val < v2_val:
                return -1
            elif v1_val > v2_val:
                return 1
        
        # Handle prerelease comparison
        v1_pre = version1.prerelease
        v2_pre = version2.prerelease
        
        # Version without prerelease > version with prerelease
        if v1_pre is None and v2_pre is not None:
            return 1
        elif v1_pre is not None and v2_pre is None:
            return -1
        elif v1_pre is None and v2_pre is None:
            return 0
        
        # Both have prerelease, compare them
        return self._compare_prerelease(v1_pre, v2_pre)
    
    def _compare_prerelease(self, pre1: str, pre2: str) -> int:
        """
        Compare prerelease versions.
        
        Args:
            pre1: First prerelease string
            pre2: Second prerelease string
            
        Returns:
            -1, 0, or 1 based on comparison
        """
        parts1 = pre1.split('.')
        parts2 = pre2.split('.')
        
        for i in range(max(len(parts1), len(parts2))):
            # If one prerelease has fewer parts, it's considered smaller
            if i >= len(parts1):
                return -1
            if i >= len(parts2):
                return 1
            
            part1, part2 = parts1[i], parts2[i]
            
            # Try to compare as integers first
            try:
                num1, num2 = int(part1), int(part2)
                if num1 < num2:
                    return -1
                elif num1 > num2:
                    return 1
            except ValueError:
                # If not both integers, compare as strings
                if part1 < part2:
                    return -1
                elif part1 > part2:
                    return 1
        
        return 0
    
    def is_newer_version(self, version1: Version, version2: Version) -> bool:
        """
        Check if version1 is newer than version2.
        
        Args:
            version1: Version to check
            version2: Version to compare against
            
        Returns:
            True if version1 is newer than version2
        """
        return self.compare_versions(version1, version2) > 0
    
    def is_compatible_version(self, current: Version, target: Version) -> bool:
        """
        Check if target version is compatible with current version.
        Compatible means same major version or higher minor/patch.
        
        Args:
            current: Current version
            target: Target version
            
        Returns:
            True if versions are compatible
        """
        # Major version must match for compatibility
        if current.major != target.major:
            return False
        
        # Target must be same or newer minor/patch version
        return self.compare_versions(target, current) >= 0
    
    def get_current_version(self) -> Optional[Version]:
        """
        Get current agent version.
        
        Returns:
            Current version or None if not found
        """
        if self._current_version is not None:
            return self._current_version
        
        try:
            if os.path.exists(self.version_file_path):
                with open(self.version_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._current_version = Version.from_dict(data)
                    logger.info(f"Loaded current version: {self._current_version}")
            else:
                # Default version if file doesn't exist
                self._current_version = Version(0, 1, 0)
                logger.warning(f"Version file not found, using default: {self._current_version}")
        except Exception as e:
            logger.error(f"Error loading current version: {e}")
            self._current_version = Version(0, 1, 0)
        
        return self._current_version
    
    def save_version(self, version: Version) -> bool:
        """
        Save version to file.
        
        Args:
            version: Version to save
            
        Returns:
            True if saved successfully
        """
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.version_file_path) or '.', exist_ok=True)
            
            with open(self.version_file_path, 'w', encoding='utf-8') as f:
                json.dump(version.to_dict(), f, indent=2)
            
            self._current_version = version
            logger.info(f"Saved version: {version}")
            return True
        except Exception as e:
            logger.error(f"Error saving version: {e}")
            return False
    
    def update_version(self, new_version: Version) -> bool:
        """
        Update current version to new version.
        
        Args:
            new_version: New version to update to
            
        Returns:
            True if updated successfully
        """
        current = self.get_current_version()
        if current is None:
            logger.error("Cannot get current version")
            return False
        
        if not self.is_newer_version(new_version, current):
            logger.warning(f"New version {new_version} is not newer than current {current}")
            return False
        
        return self.save_version(new_version)
    
    def get_version_info(self) -> Dict[str, Any]:
        """
        Get comprehensive version information.
        
        Returns:
            Dictionary containing version information
        """
        current = self.get_current_version()
        if current is None:
            return {"error": "Cannot get current version"}
        
        return {
            "current_version": str(current),
            "version_details": current.to_dict(),
            "version_file": self.version_file_path,
            "is_prerelease": current.prerelease is not None
        }
    
    def validate_version_string(self, version_string: str) -> Tuple[bool, Optional[str]]:
        """
        Validate version string format.
        
        Args:
            version_string: Version string to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            self.parse_version(version_string)
            return True, None
        except ValueError as e:
            return False, str(e)
    
    def get_next_version(self, version_type: VersionType, 
                        prerelease: Optional[str] = None) -> Version:
        """
        Get next version based on current version and increment type.
        
        Args:
            version_type: Type of version increment
            prerelease: Optional prerelease identifier
            
        Returns:
            Next version
        """
        current = self.get_current_version()
        if current is None:
            raise ValueError("Cannot get current version")
        
        if version_type == VersionType.MAJOR:
            return Version(current.major + 1, 0, 0, prerelease)
        elif version_type == VersionType.MINOR:
            return Version(current.major, current.minor + 1, 0, prerelease)
        elif version_type == VersionType.PATCH:
            return Version(current.major, current.minor, current.patch + 1, prerelease)
        elif version_type == VersionType.PRERELEASE:
            if current.prerelease:
                # Increment prerelease
                parts = current.prerelease.split('.')
                if parts[-1].isdigit():
                    parts[-1] = str(int(parts[-1]) + 1)
                else:
                    parts.append('1')
                new_prerelease = '.'.join(parts)
            else:
                new_prerelease = prerelease or 'alpha.1'
            
            return Version(current.major, current.minor, current.patch, new_prerelease)
        else:
            raise ValueError(f"Unknown version type: {version_type}")