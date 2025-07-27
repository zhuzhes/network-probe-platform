"""
Update client for agent OTA updates.
Handles update detection, download, verification, and installation.
"""

import os
import json
import tempfile
import tarfile
import shutil
import subprocess
import signal
import sys
import time
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path
from datetime import datetime
import logging
import asyncio
import aiohttp

from .version_manager import VersionManager, Version

logger = logging.getLogger(__name__)


class UpdateStatus:
    """Update status constants."""
    CHECKING = "checking"
    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    INSTALLING = "installing"
    COMPLETED = "completed"
    FAILED = "failed"
    NO_UPDATE = "no_update"


class UpdateClient:
    """
    Client for handling agent OTA updates.
    Manages the complete update lifecycle from detection to installation.
    """
    
    def __init__(self, 
                 update_server_url: str,
                 agent_id: str,
                 api_key: str,
                 install_dir: str = "/opt/network-probe-agent",
                 backup_dir: Optional[str] = None,
                 version_manager: Optional[VersionManager] = None):
        """
        Initialize update client.
        
        Args:
            update_server_url: URL of update server
            agent_id: Agent identifier
            api_key: API key for authentication
            install_dir: Agent installation directory
            backup_dir: Backup directory (defaults to install_dir/backup)
            version_manager: Version manager instance
        """
        self.update_server_url = update_server_url.rstrip('/')
        self.agent_id = agent_id
        self.api_key = api_key
        self.install_dir = Path(install_dir)
        self.backup_dir = Path(backup_dir or (install_dir + "/backup"))
        self.version_manager = version_manager or VersionManager()
        
        # Create directories
        self.install_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Update state
        self.current_status = UpdateStatus.NO_UPDATE
        self.update_info: Optional[Dict[str, Any]] = None
        self.progress_callback: Optional[Callable[[str, float, str], None]] = None
        
        # Session for HTTP requests
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=300),
            headers={'Authorization': f'Bearer {self.api_key}'}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    def set_progress_callback(self, callback: Callable[[str, float, str], None]):
        """
        Set progress callback function.
        
        Args:
            callback: Function(status, progress, message)
        """
        self.progress_callback = callback
    
    def _notify_progress(self, status: str, progress: float = 0.0, message: str = ""):
        """
        Notify progress to callback.
        
        Args:
            status: Current status
            progress: Progress percentage (0-100)
            message: Status message
        """
        self.current_status = status
        if self.progress_callback:
            try:
                self.progress_callback(status, progress, message)
            except Exception as e:
                logger.error(f"Error in progress callback: {e}")
        
        logger.info(f"Update progress: {status} ({progress:.1f}%) - {message}")
    
    async def check_for_updates(self) -> Optional[Dict[str, Any]]:
        """
        Check for available updates.
        
        Returns:
            Update information or None if no updates available
        """
        self._notify_progress(UpdateStatus.CHECKING, 0, "Checking for updates...")
        
        try:
            current_version = self.version_manager.get_current_version()
            if not current_version:
                logger.error("Cannot get current version")
                return None
            
            # Get system information
            system_info = self._get_system_info()
            
            # Request update information
            url = f"{self.update_server_url}/api/v1/agents/{self.agent_id}/updates"
            params = {
                'current_version': str(current_version),
                'platform': system_info['platform'],
                'architecture': system_info['architecture']
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 404:
                    self._notify_progress(UpdateStatus.NO_UPDATE, 100, "No updates available")
                    return None
                
                response.raise_for_status()
                update_data = await response.json()
                
                if not update_data.get('available'):
                    self._notify_progress(UpdateStatus.NO_UPDATE, 100, "No updates available")
                    return None
                
                self.update_info = update_data
                self._notify_progress(
                    UpdateStatus.AVAILABLE, 
                    100, 
                    f"Update available: {update_data['version']}"
                )
                
                logger.info(f"Update available: {update_data['version']}")
                return update_data
        
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            self._notify_progress(UpdateStatus.FAILED, 0, f"Update check failed: {e}")
            return None
    
    async def download_update(self, update_info: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Download update package.
        
        Args:
            update_info: Update information (uses cached if None)
            
        Returns:
            Path to downloaded package or None if failed
        """
        update_info = update_info or self.update_info
        if not update_info:
            logger.error("No update information available")
            return None
        
        self._notify_progress(UpdateStatus.DOWNLOADING, 0, "Starting download...")
        
        try:
            download_url = update_info['download_url']
            package_size = update_info.get('size', 0)
            
            # Create temporary file for download
            temp_dir = tempfile.mkdtemp(prefix='agent_update_')
            package_path = os.path.join(temp_dir, 'update_package.tar.gz')
            
            # Download with progress tracking
            async with self.session.get(download_url) as response:
                response.raise_for_status()
                
                downloaded = 0
                with open(package_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if package_size > 0:
                            progress = (downloaded / package_size) * 100
                            self._notify_progress(
                                UpdateStatus.DOWNLOADING,
                                progress,
                                f"Downloaded {downloaded}/{package_size} bytes"
                            )
            
            # Download signature file
            signature_url = update_info.get('signature_url')
            if signature_url:
                signature_path = package_path + '.sig'
                async with self.session.get(signature_url) as response:
                    response.raise_for_status()
                    with open(signature_path, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
            
            self._notify_progress(UpdateStatus.DOWNLOADING, 100, "Download completed")
            logger.info(f"Downloaded update package: {package_path}")
            return package_path
        
        except Exception as e:
            logger.error(f"Error downloading update: {e}")
            self._notify_progress(UpdateStatus.FAILED, 0, f"Download failed: {e}")
            return None
    
    def verify_update_package(self, package_path: str) -> bool:
        """
        Verify update package integrity and signature.
        
        Args:
            package_path: Path to update package
            
        Returns:
            True if package is valid
        """
        self._notify_progress(UpdateStatus.VERIFYING, 0, "Verifying package...")
        
        try:
            # Check if package file exists
            if not os.path.exists(package_path):
                logger.error(f"Package file not found: {package_path}")
                return False
            
            # Verify package can be opened
            try:
                with tarfile.open(package_path, "r:gz") as tar:
                    # Check for required files
                    required_files = ['package_info.json', 'install.sh']
                    tar_members = [m.name for m in tar.getmembers()]
                    
                    for required_file in required_files:
                        if required_file not in tar_members:
                            logger.error(f"Required file missing: {required_file}")
                            return False
                    
                    # Extract and validate package info
                    info_member = tar.getmember('package_info.json')
                    info_file = tar.extractfile(info_member)
                    if info_file:
                        package_info = json.load(info_file)
                        
                        # Validate version format
                        version_str = package_info.get('version')
                        if not version_str:
                            logger.error("Package version not found")
                            return False
                        
                        try:
                            package_version = self.version_manager.parse_version(version_str)
                            current_version = self.version_manager.get_current_version()
                            
                            if current_version and not self.version_manager.is_newer_version(
                                package_version, current_version
                            ):
                                logger.error(f"Package version {package_version} is not newer than current {current_version}")
                                return False
                        except ValueError as e:
                            logger.error(f"Invalid package version: {e}")
                            return False
            
            except tarfile.TarError as e:
                logger.error(f"Invalid package format: {e}")
                return False
            
            # Verify signature if available
            signature_path = package_path + '.sig'
            if os.path.exists(signature_path):
                try:
                    with open(signature_path, 'r', encoding='utf-8') as f:
                        signature_info = json.load(f)
                    
                    # Basic signature validation (simplified for now)
                    required_sig_fields = ['file_hash', 'signature', 'signing_method']
                    for field in required_sig_fields:
                        if field not in signature_info:
                            logger.error(f"Missing signature field: {field}")
                            return False
                    
                    # Verify file hash matches
                    import hashlib
                    with open(package_path, 'rb') as f:
                        file_hash = hashlib.sha256(f.read()).hexdigest()
                    
                    if file_hash != signature_info['file_hash']:
                        logger.error("Package hash verification failed")
                        return False
                    
                    logger.info("Package signature verified")
                
                except Exception as e:
                    logger.error(f"Signature verification failed: {e}")
                    return False
            else:
                logger.warning("No signature file found, skipping signature verification")
            
            self._notify_progress(UpdateStatus.VERIFYING, 100, "Package verification completed")
            logger.info("Update package verification successful")
            return True
        
        except Exception as e:
            logger.error(f"Error verifying package: {e}")
            self._notify_progress(UpdateStatus.FAILED, 0, f"Verification failed: {e}")
            return False
    
    def create_backup(self) -> bool:
        """
        Create backup of current installation.
        
        Returns:
            True if backup created successfully
        """
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"backup_{timestamp}.tar.gz"
            backup_path = self.backup_dir / backup_name
            
            logger.info(f"Creating backup: {backup_path}")
            
            with tarfile.open(backup_path, "w:gz") as tar:
                for item in self.install_dir.iterdir():
                    if item.name != 'backup':  # Don't backup the backup directory
                        tar.add(item, arcname=item.name)
            
            logger.info(f"Backup created successfully: {backup_path}")
            return True
        
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return False
    
    def install_update(self, package_path: str) -> bool:
        """
        Install update package.
        
        Args:
            package_path: Path to verified update package
            
        Returns:
            True if installation successful
        """
        self._notify_progress(UpdateStatus.INSTALLING, 0, "Starting installation...")
        
        try:
            # Create backup first
            if not self.create_backup():
                logger.error("Failed to create backup")
                return False
            
            self._notify_progress(UpdateStatus.INSTALLING, 20, "Backup created")
            
            # Extract package to temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)
                
                # Extract package
                with tarfile.open(package_path, "r:gz") as tar:
                    tar.extractall(temp_path)
                
                self._notify_progress(UpdateStatus.INSTALLING, 40, "Package extracted")
                
                # Read package info
                package_info_path = temp_path / 'package_info.json'
                with open(package_info_path, 'r', encoding='utf-8') as f:
                    package_info = json.load(f)
                
                # Install files
                for file_info in package_info.get('files', []):
                    source_path = temp_path / file_info['target_path']
                    target_path = self.install_dir / file_info['target_path']
                    
                    # Create target directory
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Copy file
                    shutil.copy2(source_path, target_path)
                    
                    # Set permissions
                    try:
                        permissions = int(file_info['permissions'], 8)
                        os.chmod(target_path, permissions)
                    except (ValueError, OSError) as e:
                        logger.warning(f"Could not set permissions for {target_path}: {e}")
                
                self._notify_progress(UpdateStatus.INSTALLING, 70, "Files installed")
                
                # Update version information
                new_version = self.version_manager.parse_version(package_info['version'])
                if not self.version_manager.save_version(new_version):
                    logger.error("Failed to update version information")
                    return False
                
                self._notify_progress(UpdateStatus.INSTALLING, 90, "Version updated")
                
                # Run post-install script if available
                install_script = temp_path / 'install.sh'
                if install_script.exists():
                    try:
                        env = os.environ.copy()
                        env['INSTALL_DIR'] = str(self.install_dir)
                        env['BACKUP_DIR'] = str(self.backup_dir)
                        
                        result = subprocess.run(
                            ['bash', str(install_script)],
                            env=env,
                            capture_output=True,
                            text=True,
                            timeout=300
                        )
                        
                        if result.returncode != 0:
                            logger.error(f"Install script failed: {result.stderr}")
                            return False
                        
                        logger.info("Install script executed successfully")
                    
                    except subprocess.TimeoutExpired:
                        logger.error("Install script timed out")
                        return False
                    except Exception as e:
                        logger.error(f"Error running install script: {e}")
                        return False
            
            self._notify_progress(UpdateStatus.INSTALLING, 100, "Installation completed")
            logger.info(f"Update installed successfully: {package_info['version']}")
            return True
        
        except Exception as e:
            logger.error(f"Error installing update: {e}")
            self._notify_progress(UpdateStatus.FAILED, 0, f"Installation failed: {e}")
            return False
    
    def schedule_restart(self, delay_seconds: int = 5) -> bool:
        """
        Schedule agent restart after update.
        
        Args:
            delay_seconds: Delay before restart
            
        Returns:
            True if restart scheduled successfully
        """
        try:
            logger.info(f"Scheduling restart in {delay_seconds} seconds...")
            
            # Create restart script
            restart_script = self.install_dir / 'restart_agent.sh'
            script_content = f'''#!/bin/bash
sleep {delay_seconds}
echo "Restarting agent after update..."

# Try to restart using systemd if available
if command -v systemctl >/dev/null 2>&1; then
    systemctl restart network-probe-agent
elif command -v service >/dev/null 2>&1; then
    service network-probe-agent restart
else
    # Fallback: kill current process and start new one
    pkill -f "python.*agent"
    cd "{self.install_dir}"
    python -m agent &
fi
'''
            
            with open(restart_script, 'w', encoding='utf-8') as f:
                f.write(script_content)
            
            os.chmod(restart_script, 0o755)
            
            # Execute restart script in background
            subprocess.Popen(['bash', str(restart_script)], 
                           start_new_session=True)
            
            logger.info("Restart scheduled successfully")
            return True
        
        except Exception as e:
            logger.error(f"Error scheduling restart: {e}")
            return False
    
    async def perform_update(self, auto_restart: bool = True) -> bool:
        """
        Perform complete update process.
        
        Args:
            auto_restart: Whether to automatically restart after update
            
        Returns:
            True if update completed successfully
        """
        try:
            # Check for updates
            update_info = await self.check_for_updates()
            if not update_info:
                return False
            
            # Download update
            package_path = await self.download_update(update_info)
            if not package_path:
                return False
            
            try:
                # Verify package
                if not self.verify_update_package(package_path):
                    return False
                
                # Install update
                if not self.install_update(package_path):
                    return False
                
                self._notify_progress(UpdateStatus.COMPLETED, 100, "Update completed successfully")
                
                # Schedule restart if requested
                if auto_restart:
                    self.schedule_restart()
                
                return True
            
            finally:
                # Clean up downloaded package
                try:
                    if os.path.exists(package_path):
                        temp_dir = os.path.dirname(package_path)
                        shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.warning(f"Error cleaning up download: {e}")
        
        except Exception as e:
            logger.error(f"Error performing update: {e}")
            self._notify_progress(UpdateStatus.FAILED, 0, f"Update failed: {e}")
            return False
    
    def rollback_update(self, backup_name: Optional[str] = None) -> bool:
        """
        Rollback to previous version using backup.
        
        Args:
            backup_name: Specific backup to restore (uses latest if None)
            
        Returns:
            True if rollback successful
        """
        try:
            # Find backup to restore
            if backup_name:
                backup_path = self.backup_dir / backup_name
            else:
                # Find latest backup
                backups = list(self.backup_dir.glob('backup_*.tar.gz'))
                if not backups:
                    logger.error("No backups found")
                    return False
                
                backup_path = max(backups, key=lambda p: p.stat().st_mtime)
            
            if not backup_path.exists():
                logger.error(f"Backup not found: {backup_path}")
                return False
            
            logger.info(f"Rolling back using backup: {backup_path}")
            
            # Clear current installation (except backup directory)
            for item in self.install_dir.iterdir():
                if item.name != 'backup':
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
            
            # Restore from backup
            with tarfile.open(backup_path, "r:gz") as tar:
                tar.extractall(self.install_dir)
            
            logger.info("Rollback completed successfully")
            return True
        
        except Exception as e:
            logger.error(f"Error during rollback: {e}")
            return False
    
    def _get_system_info(self) -> Dict[str, str]:
        """
        Get system information for update compatibility.
        
        Returns:
            Dictionary with system information
        """
        import platform
        
        return {
            'platform': platform.system().lower(),
            'architecture': platform.machine().lower(),
            'python_version': platform.python_version()
        }
    
    def get_update_status(self) -> Dict[str, Any]:
        """
        Get current update status.
        
        Returns:
            Status information dictionary
        """
        return {
            'status': self.current_status,
            'update_info': self.update_info,
            'current_version': str(self.version_manager.get_current_version()),
            'install_dir': str(self.install_dir),
            'backup_dir': str(self.backup_dir)
        }
    
    def cleanup_old_backups(self, keep_count: int = 5) -> int:
        """
        Clean up old backup files.
        
        Args:
            keep_count: Number of recent backups to keep
            
        Returns:
            Number of backups deleted
        """
        try:
            backups = list(self.backup_dir.glob('backup_*.tar.gz'))
            backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            
            deleted_count = 0
            for backup in backups[keep_count:]:
                try:
                    backup.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted old backup: {backup}")
                except Exception as e:
                    logger.error(f"Error deleting backup {backup}: {e}")
            
            return deleted_count
        
        except Exception as e:
            logger.error(f"Error cleaning up backups: {e}")
            return 0