"""
Unit tests for version manager module.
"""

import pytest
import json
import os
import tempfile
from unittest.mock import patch, mock_open

from agent.updater.version_manager import (
    VersionManager, Version, VersionType
)


class TestVersion:
    """Test Version class."""
    
    def test_version_creation(self):
        """Test version object creation."""
        version = Version(1, 2, 3)
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3
        assert version.prerelease is None
        assert version.build_metadata is None
    
    def test_version_with_prerelease(self):
        """Test version with prerelease."""
        version = Version(1, 2, 3, "alpha.1")
        assert version.prerelease == "alpha.1"
    
    def test_version_with_build_metadata(self):
        """Test version with build metadata."""
        version = Version(1, 2, 3, build_metadata="build.123")
        assert version.build_metadata == "build.123"
    
    def test_version_string_representation(self):
        """Test version string representation."""
        # Basic version
        version = Version(1, 2, 3)
        assert str(version) == "1.2.3"
        
        # With prerelease
        version = Version(1, 2, 3, "alpha.1")
        assert str(version) == "1.2.3-alpha.1"
        
        # With build metadata
        version = Version(1, 2, 3, build_metadata="build.123")
        assert str(version) == "1.2.3+build.123"
        
        # With both
        version = Version(1, 2, 3, "beta.2", "build.456")
        assert str(version) == "1.2.3-beta.2+build.456"
    
    def test_version_to_dict(self):
        """Test version to dictionary conversion."""
        version = Version(1, 2, 3, "alpha.1", "build.123")
        expected = {
            "major": 1,
            "minor": 2,
            "patch": 3,
            "prerelease": "alpha.1",
            "build_metadata": "build.123"
        }
        assert version.to_dict() == expected
    
    def test_version_from_dict(self):
        """Test version from dictionary creation."""
        data = {
            "major": 1,
            "minor": 2,
            "patch": 3,
            "prerelease": "alpha.1",
            "build_metadata": "build.123"
        }
        version = Version.from_dict(data)
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3
        assert version.prerelease == "alpha.1"
        assert version.build_metadata == "build.123"


class TestVersionManager:
    """Test VersionManager class."""
    
    def setup_method(self):
        """Set up test method."""
        self.temp_dir = tempfile.mkdtemp()
        self.version_file = os.path.join(self.temp_dir, "version.json")
        self.manager = VersionManager(self.version_file)
    
    def teardown_method(self):
        """Clean up after test method."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_parse_version_basic(self):
        """Test basic version parsing."""
        version = self.manager.parse_version("1.2.3")
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3
        assert version.prerelease is None
        assert version.build_metadata is None
    
    def test_parse_version_with_prerelease(self):
        """Test version parsing with prerelease."""
        version = self.manager.parse_version("1.2.3-alpha.1")
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3
        assert version.prerelease == "alpha.1"
    
    def test_parse_version_with_build_metadata(self):
        """Test version parsing with build metadata."""
        version = self.manager.parse_version("1.2.3+build.123")
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3
        assert version.build_metadata == "build.123"
    
    def test_parse_version_complex(self):
        """Test complex version parsing."""
        version = self.manager.parse_version("1.2.3-beta.2+build.456")
        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3
        assert version.prerelease == "beta.2"
        assert version.build_metadata == "build.456"
    
    def test_parse_version_invalid(self):
        """Test invalid version parsing."""
        with pytest.raises(ValueError):
            self.manager.parse_version("invalid.version")
        
        with pytest.raises(ValueError):
            self.manager.parse_version("1.2")
        
        with pytest.raises(ValueError):
            self.manager.parse_version("1.2.3.4")
    
    def test_compare_versions_basic(self):
        """Test basic version comparison."""
        v1 = Version(1, 2, 3)
        v2 = Version(1, 2, 4)
        v3 = Version(1, 3, 0)
        v4 = Version(2, 0, 0)
        
        assert self.manager.compare_versions(v1, v2) == -1  # v1 < v2
        assert self.manager.compare_versions(v2, v1) == 1   # v2 > v1
        assert self.manager.compare_versions(v1, v1) == 0   # v1 == v1
        
        assert self.manager.compare_versions(v1, v3) == -1  # v1 < v3
        assert self.manager.compare_versions(v1, v4) == -1  # v1 < v4
    
    def test_compare_versions_with_prerelease(self):
        """Test version comparison with prerelease."""
        v1 = Version(1, 2, 3)
        v2 = Version(1, 2, 3, "alpha.1")
        v3 = Version(1, 2, 3, "alpha.2")
        v4 = Version(1, 2, 3, "beta.1")
        
        # Version without prerelease > version with prerelease
        assert self.manager.compare_versions(v1, v2) == 1
        assert self.manager.compare_versions(v2, v1) == -1
        
        # Compare prerelease versions
        assert self.manager.compare_versions(v2, v3) == -1  # alpha.1 < alpha.2
        assert self.manager.compare_versions(v2, v4) == -1  # alpha.1 < beta.1
    
    def test_is_newer_version(self):
        """Test is_newer_version method."""
        v1 = Version(1, 2, 3)
        v2 = Version(1, 2, 4)
        v3 = Version(1, 2, 3, "alpha.1")
        
        assert self.manager.is_newer_version(v2, v1) is True
        assert self.manager.is_newer_version(v1, v2) is False
        assert self.manager.is_newer_version(v1, v3) is True  # release > prerelease
    
    def test_is_compatible_version(self):
        """Test is_compatible_version method."""
        v1 = Version(1, 2, 3)
        v2 = Version(1, 2, 4)  # Same major, newer minor/patch
        v3 = Version(1, 3, 0)  # Same major, newer minor
        v4 = Version(2, 0, 0)  # Different major
        v5 = Version(1, 2, 2)  # Same major, older patch
        
        assert self.manager.is_compatible_version(v1, v2) is True
        assert self.manager.is_compatible_version(v1, v3) is True
        assert self.manager.is_compatible_version(v1, v4) is False  # Different major
        assert self.manager.is_compatible_version(v1, v5) is False  # Older version
    
    def test_get_current_version_file_not_exists(self):
        """Test get_current_version when file doesn't exist."""
        version = self.manager.get_current_version()
        assert version is not None
        assert version.major == 0
        assert version.minor == 1
        assert version.patch == 0
    
    def test_get_current_version_file_exists(self):
        """Test get_current_version when file exists."""
        # Create version file
        version_data = {
            "major": 2,
            "minor": 3,
            "patch": 4,
            "prerelease": "beta.1",
            "build_metadata": None
        }
        with open(self.version_file, 'w') as f:
            json.dump(version_data, f)
        
        version = self.manager.get_current_version()
        assert version.major == 2
        assert version.minor == 3
        assert version.patch == 4
        assert version.prerelease == "beta.1"
    
    def test_save_version(self):
        """Test save_version method."""
        version = Version(1, 2, 3, "alpha.1")
        result = self.manager.save_version(version)
        
        assert result is True
        assert os.path.exists(self.version_file)
        
        # Verify file content
        with open(self.version_file, 'r') as f:
            data = json.load(f)
        
        expected = {
            "major": 1,
            "minor": 2,
            "patch": 3,
            "prerelease": "alpha.1",
            "build_metadata": None
        }
        assert data == expected
    
    def test_update_version_success(self):
        """Test successful version update."""
        # Set current version
        current = Version(1, 2, 3)
        self.manager.save_version(current)
        
        # Update to newer version
        new_version = Version(1, 2, 4)
        result = self.manager.update_version(new_version)
        
        assert result is True
        assert self.manager.get_current_version().patch == 4
    
    def test_update_version_not_newer(self):
        """Test version update with non-newer version."""
        # Set current version
        current = Version(1, 2, 3)
        self.manager.save_version(current)
        
        # Try to update to older version
        old_version = Version(1, 2, 2)
        result = self.manager.update_version(old_version)
        
        assert result is False
        assert self.manager.get_current_version().patch == 3  # Unchanged
    
    def test_get_version_info(self):
        """Test get_version_info method."""
        version = Version(1, 2, 3, "alpha.1")
        self.manager.save_version(version)
        
        info = self.manager.get_version_info()
        
        assert info["current_version"] == "1.2.3-alpha.1"
        assert info["version_details"]["major"] == 1
        assert info["version_details"]["minor"] == 2
        assert info["version_details"]["patch"] == 3
        assert info["version_details"]["prerelease"] == "alpha.1"
        assert info["is_prerelease"] is True
        assert info["version_file"] == self.version_file
    
    def test_validate_version_string_valid(self):
        """Test validate_version_string with valid strings."""
        valid_versions = [
            "1.2.3",
            "1.2.3-alpha.1",
            "1.2.3+build.123",
            "1.2.3-beta.2+build.456",
            "0.0.1",
            "10.20.30"
        ]
        
        for version_str in valid_versions:
            is_valid, error = self.manager.validate_version_string(version_str)
            assert is_valid is True, f"Version {version_str} should be valid"
            assert error is None
    
    def test_validate_version_string_invalid(self):
        """Test validate_version_string with invalid strings."""
        invalid_versions = [
            "1.2",
            "1.2.3.4",
            "invalid",
            "1.2.3-",
            "1.2.3+",
            ""
        ]
        
        for version_str in invalid_versions:
            is_valid, error = self.manager.validate_version_string(version_str)
            assert is_valid is False, f"Version {version_str} should be invalid"
            assert error is not None
    
    def test_get_next_version_major(self):
        """Test get_next_version for major increment."""
        current = Version(1, 2, 3)
        self.manager.save_version(current)
        
        next_version = self.manager.get_next_version(VersionType.MAJOR)
        assert next_version.major == 2
        assert next_version.minor == 0
        assert next_version.patch == 0
        assert next_version.prerelease is None
    
    def test_get_next_version_minor(self):
        """Test get_next_version for minor increment."""
        current = Version(1, 2, 3)
        self.manager.save_version(current)
        
        next_version = self.manager.get_next_version(VersionType.MINOR)
        assert next_version.major == 1
        assert next_version.minor == 3
        assert next_version.patch == 0
        assert next_version.prerelease is None
    
    def test_get_next_version_patch(self):
        """Test get_next_version for patch increment."""
        current = Version(1, 2, 3)
        self.manager.save_version(current)
        
        next_version = self.manager.get_next_version(VersionType.PATCH)
        assert next_version.major == 1
        assert next_version.minor == 2
        assert next_version.patch == 4
        assert next_version.prerelease is None
    
    def test_get_next_version_prerelease(self):
        """Test get_next_version for prerelease increment."""
        # Test with no current prerelease
        current = Version(1, 2, 3)
        self.manager.save_version(current)
        
        next_version = self.manager.get_next_version(VersionType.PRERELEASE, "alpha.1")
        assert next_version.major == 1
        assert next_version.minor == 2
        assert next_version.patch == 3
        assert next_version.prerelease == "alpha.1"
        
        # Test with existing prerelease
        current = Version(1, 2, 3, "alpha.1")
        self.manager.save_version(current)
        
        next_version = self.manager.get_next_version(VersionType.PRERELEASE)
        assert next_version.prerelease == "alpha.2"
    
    def test_get_next_version_with_prerelease_param(self):
        """Test get_next_version with prerelease parameter."""
        current = Version(1, 2, 3)
        self.manager.save_version(current)
        
        next_version = self.manager.get_next_version(VersionType.MAJOR, "beta.1")
        assert next_version.major == 2
        assert next_version.minor == 0
        assert next_version.patch == 0
        assert next_version.prerelease == "beta.1"
    
    def test_compare_prerelease_numeric(self):
        """Test prerelease comparison with numeric parts."""
        result = self.manager._compare_prerelease("alpha.1", "alpha.2")
        assert result == -1
        
        result = self.manager._compare_prerelease("alpha.10", "alpha.2")
        assert result == 1
    
    def test_compare_prerelease_mixed(self):
        """Test prerelease comparison with mixed parts."""
        result = self.manager._compare_prerelease("alpha.1", "beta.1")
        assert result == -1
        
        result = self.manager._compare_prerelease("alpha", "alpha.1")
        assert result == -1
    
    @patch('builtins.open', side_effect=IOError("File error"))
    def test_save_version_error(self, mock_file):
        """Test save_version with file error."""
        version = Version(1, 2, 3)
        result = self.manager.save_version(version)
        assert result is False
    
    @patch('builtins.open', mock_open(read_data='invalid json'))
    def test_get_current_version_invalid_json(self):
        """Test get_current_version with invalid JSON."""
        with patch('os.path.exists', return_value=True):
            version = self.manager.get_current_version()
            # Should return default version on error
            assert version.major == 0
            assert version.minor == 1
            assert version.patch == 0