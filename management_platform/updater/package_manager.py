"""
Update package manager for creating, storing, and distributing agent updates.
Handles the complete lifecycle of update packages including creation, signing, and distribution.
"""

import os
import json
import shutil
import tempfile
import tarfile
import zipfile
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
import logging

from .signature_manager import SignatureManager
from agent.updater.version_manager import VersionManager, Version

logger = logging.getLogger(__name__)


class UpdatePackageManager:
    """
    Manages update packages for agent OTA updates.
    Handles package creation, signing, storage, and distribution.
    """
    
    def __init__(self, storage_path: str = "updates", 
                 signature_manager: Optional[SignatureManager] = None):
        """
        Initialize update package manager.
        
        Args:
            storage_path: Path to store update packages
            signature_manager: Signature manager for package signing
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.signature_manager = signature_manager or SignatureManager()
        self.version_manager = VersionManager()
    
    def create_package_info(self, version: Version, description: str = "",
                           changelog: List[str] = None,
                           compatibility: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Create package information structure.
        
        Args:
            version: Package version
            description: Package description
            changelog: List of changes
            compatibility: Compatibility requirements
            
        Returns:
            Package information dictionary
        """
        return {
            "version": str(version),
            "version_details": version.to_dict(),
            "description": description,
            "changelog": changelog or [],
            "created_at": datetime.utcnow().isoformat(),
            "compatibility": compatibility or {
                "min_version": "0.1.0",
                "max_version": None,
                "platforms": ["linux", "darwin", "windows"],
                "architectures": ["x86_64", "arm64"]
            },
            "package_type": "full",  # full, incremental
            "compression": "gzip",
            "files": []
        }
    
    def add_file_to_package(self, package_info: Dict[str, Any], 
                           source_path: str, target_path: str,
                           file_type: str = "binary") -> bool:
        """
        Add file to package information.
        
        Args:
            package_info: Package information dictionary
            source_path: Source file path
            target_path: Target path in package
            file_type: File type (binary, config, script)
            
        Returns:
            True if added successfully
        """
        if not os.path.exists(source_path):
            logger.error(f"Source file not found: {source_path}")
            return False
        
        try:
            file_info = {
                "source_path": source_path,
                "target_path": target_path,
                "file_type": file_type,
                "size": os.path.getsize(source_path),
                "permissions": oct(os.stat(source_path).st_mode)[-3:],
                "hash": self.signature_manager.calculate_file_hash(source_path)
            }
            
            package_info["files"].append(file_info)
            logger.info(f"Added file to package: {source_path} -> {target_path}")
            return True
        
        except Exception as e:
            logger.error(f"Error adding file to package: {e}")
            return False
    
    def create_update_package(self, package_info: Dict[str, Any],
                             output_path: Optional[str] = None) -> Optional[str]:
        """
        Create update package archive.
        
        Args:
            package_info: Package information
            output_path: Output package path (auto-generated if None)
            
        Returns:
            Path to created package or None if failed
        """
        version = package_info["version"]
        if not output_path:
            output_path = self.storage_path / f"agent-update-{version}.tar.gz"
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Create package structure
                package_dir = temp_path / "package"
                package_dir.mkdir()
                
                # Copy files to package
                for file_info in package_info["files"]:
                    source = file_info["source_path"]
                    target = package_dir / file_info["target_path"]
                    
                    # Create target directory
                    target.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy file
                    shutil.copy2(source, target)
                    
                    # Set permissions
                    try:
                        os.chmod(target, int(file_info["permissions"], 8))
                    except (ValueError, OSError) as e:
                        logger.warning(f"Could not set permissions for {target}: {e}")
                
                # Create package info file
                info_file = package_dir / "package_info.json"
                with open(info_file, 'w', encoding='utf-8') as f:
                    json.dump(package_info, f, indent=2)
                
                # Create installation script
                install_script = package_dir / "install.sh"
                self._create_install_script(install_script, package_info)
                os.chmod(install_script, 0o755)
                
                # Create package archive
                with tarfile.open(output_path, "w:gz") as tar:
                    for item in package_dir.iterdir():
                        tar.add(item, arcname=item.name)
                
                logger.info(f"Created update package: {output_path}")
                return str(output_path)
        
        except Exception as e:
            logger.error(f"Error creating update package: {e}")
            return None
    
    def _create_install_script(self, script_path: Path, 
                              package_info: Dict[str, Any]) -> None:
        """
        Create installation script for update package.
        
        Args:
            script_path: Path to create script
            package_info: Package information
        """
        script_content = f'''#!/bin/bash
# Agent Update Installation Script
# Version: {package_info["version"]}
# Created: {package_info["created_at"]}

set -e

INSTALL_DIR="${{INSTALL_DIR:-/opt/network-probe-agent}}"
BACKUP_DIR="${{BACKUP_DIR:-$INSTALL_DIR/backup}}"
LOG_FILE="${{LOG_FILE:-/var/log/agent-update.log}}"

log() {{
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG_FILE"
}}

log "Starting agent update installation..."
log "Target version: {package_info["version"]}"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup current installation
if [ -d "$INSTALL_DIR" ]; then
    log "Creating backup of current installation..."
    tar -czf "$BACKUP_DIR/backup-$(date +%Y%m%d-%H%M%S).tar.gz" -C "$INSTALL_DIR" . || true
fi

# Create installation directory
mkdir -p "$INSTALL_DIR"

# Install files
'''
        
        for file_info in package_info["files"]:
            target_path = file_info["target_path"]
            permissions = file_info["permissions"]
            
            script_content += f'''
# Install {target_path}
cp "{target_path}" "$INSTALL_DIR/{target_path}"
chmod {permissions} "$INSTALL_DIR/{target_path}"
'''
        
        script_content += '''
# Update version information
echo '{"version": "''' + package_info["version"] + '''", "updated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"}' > "$INSTALL_DIR/version.json"

log "Agent update installation completed successfully"
log "New version: ''' + package_info["version"] + '''"

# Restart agent service if systemd is available
if command -v systemctl >/dev/null 2>&1; then
    log "Restarting agent service..."
    systemctl restart network-probe-agent || log "Failed to restart service"
fi

exit 0
'''
        
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
    
    def sign_package(self, package_path: str, 
                    signing_method: str = 'rsa') -> Optional[Dict[str, Any]]:
        """
        Sign update package.
        
        Args:
            package_path: Path to package file
            signing_method: Signing method ('rsa' or 'hmac')
            
        Returns:
            Signature information or None if failed
        """
        try:
            signature_info = self.signature_manager.sign_file(
                package_path, signing_method
            )
            
            # Save signature to separate file
            signature_path = f"{package_path}.sig"
            with open(signature_path, 'w', encoding='utf-8') as f:
                json.dump(signature_info, f, indent=2)
            
            logger.info(f"Signed package: {package_path}")
            return signature_info
        
        except Exception as e:
            logger.error(f"Error signing package: {e}")
            return None
    
    def verify_package(self, package_path: str, 
                      signature_path: Optional[str] = None) -> bool:
        """
        Verify update package signature.
        
        Args:
            package_path: Path to package file
            signature_path: Path to signature file (auto-detected if None)
            
        Returns:
            True if package is valid
        """
        if not signature_path:
            signature_path = f"{package_path}.sig"
        
        if not os.path.exists(signature_path):
            logger.error(f"Signature file not found: {signature_path}")
            return False
        
        try:
            with open(signature_path, 'r', encoding='utf-8') as f:
                signature_info = json.load(f)
            
            return self.signature_manager.verify_file_signature(
                package_path, signature_info
            )
        
        except Exception as e:
            logger.error(f"Error verifying package: {e}")
            return False
    
    def extract_package_info(self, package_path: str) -> Optional[Dict[str, Any]]:
        """
        Extract package information from update package.
        
        Args:
            package_path: Path to package file
            
        Returns:
            Package information or None if failed
        """
        try:
            with tarfile.open(package_path, "r:gz") as tar:
                # Extract package_info.json
                info_member = tar.getmember("package_info.json")
                info_file = tar.extractfile(info_member)
                if info_file:
                    return json.load(info_file)
        
        except Exception as e:
            logger.error(f"Error extracting package info: {e}")
        
        return None
    
    def list_available_updates(self, current_version: Optional[Version] = None,
                              platform: str = "linux",
                              architecture: str = "x86_64") -> List[Dict[str, Any]]:
        """
        List available updates.
        
        Args:
            current_version: Current agent version
            platform: Target platform
            architecture: Target architecture
            
        Returns:
            List of available update packages
        """
        updates = []
        
        try:
            for package_file in self.storage_path.glob("agent-update-*.tar.gz"):
                # Check if signature exists
                signature_file = f"{package_file}.sig"
                if not os.path.exists(signature_file):
                    logger.warning(f"No signature found for {package_file}")
                    continue
                
                # Extract package info
                package_info = self.extract_package_info(str(package_file))
                if not package_info:
                    continue
                
                # Check compatibility
                compatibility = package_info.get("compatibility", {})
                if platform not in compatibility.get("platforms", []):
                    continue
                if architecture not in compatibility.get("architectures", []):
                    continue
                
                # Check version
                package_version = self.version_manager.parse_version(
                    package_info["version"]
                )
                
                if current_version and not self.version_manager.is_newer_version(
                    package_version, current_version
                ):
                    continue
                
                updates.append({
                    "package_path": str(package_file),
                    "signature_path": signature_file,
                    "package_info": package_info,
                    "version": package_version,
                    "size": os.path.getsize(package_file)
                })
        
        except Exception as e:
            logger.error(f"Error listing available updates: {e}")
        
        # Sort by version (newest first)
        from functools import cmp_to_key
        updates.sort(
            key=cmp_to_key(lambda x, y: self.version_manager.compare_versions(x["version"], y["version"])),
            reverse=True
        )
        
        return updates
    
    def get_update_info(self, version: str) -> Optional[Dict[str, Any]]:
        """
        Get information about specific update version.
        
        Args:
            version: Update version string
            
        Returns:
            Update information or None if not found
        """
        package_path = self.storage_path / f"agent-update-{version}.tar.gz"
        
        if not package_path.exists():
            return None
        
        package_info = self.extract_package_info(str(package_path))
        if not package_info:
            return None
        
        signature_path = f"{package_path}.sig"
        
        return {
            "package_path": str(package_path),
            "signature_path": signature_path,
            "package_info": package_info,
            "size": os.path.getsize(package_path),
            "signed": os.path.exists(signature_path)
        }
    
    def delete_update(self, version: str) -> bool:
        """
        Delete update package and its signature.
        
        Args:
            version: Update version to delete
            
        Returns:
            True if deleted successfully
        """
        try:
            package_path = self.storage_path / f"agent-update-{version}.tar.gz"
            signature_path = Path(f"{package_path}.sig")
            
            deleted = False
            
            if package_path.exists():
                package_path.unlink()
                deleted = True
                logger.info(f"Deleted package: {package_path}")
            
            if signature_path.exists():
                signature_path.unlink()
                deleted = True
                logger.info(f"Deleted signature: {signature_path}")
            
            return deleted
        
        except Exception as e:
            logger.error(f"Error deleting update: {e}")
            return False
    
    def cleanup_old_updates(self, keep_count: int = 5) -> int:
        """
        Clean up old update packages, keeping only the most recent ones.
        
        Args:
            keep_count: Number of recent updates to keep
            
        Returns:
            Number of packages deleted
        """
        try:
            # Get all update packages
            packages = list(self.storage_path.glob("agent-update-*.tar.gz"))
            
            # Sort by modification time (newest first)
            packages.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            
            # Delete old packages
            deleted_count = 0
            for package in packages[keep_count:]:
                version_part = package.stem.replace("agent-update-", "")
                logger.info(f"Attempting to delete version: {version_part}, package: {package}")
                try:
                    if self.delete_update(version_part):
                        deleted_count += 1
                        logger.info(f"Successfully deleted version: {version_part}")
                    else:
                        logger.warning(f"Failed to delete version: {version_part}")
                except Exception as e:
                    logger.error(f"Error deleting version {version_part}: {e}")
            
            logger.info(f"Cleaned up {deleted_count} old update packages")
            return deleted_count
        
        except Exception as e:
            logger.error(f"Error cleaning up old updates: {e}")
            return 0
    
    def get_storage_stats(self) -> Dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Storage statistics dictionary
        """
        try:
            packages = list(self.storage_path.glob("agent-update-*.tar.gz"))
            total_size = sum(p.stat().st_size for p in packages)
            
            return {
                "storage_path": str(self.storage_path),
                "total_packages": len(packages),
                "total_size": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2) if total_size > 0 else 0.0,
                "packages": [
                    {
                        "name": p.name,
                        "size": p.stat().st_size,
                        "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat()
                    }
                    for p in packages
                ]
            }
        
        except Exception as e:
            logger.error(f"Error getting storage stats: {e}")
            return {"error": str(e)}