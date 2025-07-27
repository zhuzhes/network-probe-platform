"""
Unit tests for update client functionality.
Tests update detection, download, verification, and installation processes.
"""

import pytest
import asyncio
import json
import tempfile
import tarfile
import os
import shutil
import subprocess
import time
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import aiohttp

from agent.updater.update_client import UpdateClient, UpdateStatus
from agent.updater.version_manager import VersionManager, Version


class TestUpdateClient:
    """Test cases for UpdateClient."""
    
    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        install_dir = tempfile.mkdtemp(prefix='test_install_')
        backup_dir = tempfile.mkdtemp(prefix='test_backup_')
        
        yield install_dir, backup_dir
        
        # Cleanup
        shutil.rmtree(install_dir, ignore_errors=True)
        shutil.rmtree(backup_dir, ignore_errors=True)
    
    @pytest.fixture
    def mock_version_manager(self):
        """Mock version manager."""
        version_manager = Mock(spec=VersionManager)
        version_manager.get_current_version.return_value = Version(1, 0, 0)
        version_manager.parse_version.return_value = Version(1, 1, 0)
        version_manager.is_newer_version.return_value = True
        version_manager.save_version.return_value = True
        return version_manager
    
    @pytest.fixture
    def update_client(self, temp_dirs, mock_version_manager):
        """Create update client for testing."""
        install_dir, backup_dir = temp_dirs
        
        client = UpdateClient(
            update_server_url="https://update.example.com",
            agent_id="test-agent-123",
            api_key="test-api-key",
            install_dir=install_dir,
            backup_dir=backup_dir,
            version_manager=mock_version_manager
        )
        
        return client
    
    @pytest.fixture
    def sample_update_info(self):
        """Sample update information."""
        return {
            'available': True,
            'version': '1.1.0',
            'description': 'Test update',
            'download_url': 'https://update.example.com/packages/agent-update-1.1.0.tar.gz',
            'signature_url': 'https://update.example.com/packages/agent-update-1.1.0.tar.gz.sig',
            'size': 1024000,
            'changelog': ['Bug fixes', 'Performance improvements']
        }
    
    @pytest.fixture
    def sample_package(self, temp_dirs):
        """Create sample update package."""
        install_dir, _ = temp_dirs
        
        # Create package content
        package_dir = Path(tempfile.mkdtemp(prefix='test_package_'))
        
        # Create package info
        package_info = {
            'version': '1.1.0',
            'description': 'Test update',
            'created_at': '2024-01-01T00:00:00Z',
            'files': [
                {
                    'source_path': 'agent.py',
                    'target_path': 'agent.py',
                    'file_type': 'binary',
                    'size': 1000,
                    'permissions': '755',
                    'hash': 'abcd1234'
                }
            ]
        }
        
        with open(package_dir / 'package_info.json', 'w') as f:
            json.dump(package_info, f)
        
        # Create install script
        install_script = package_dir / 'install.sh'
        install_script.write_text('#!/bin/bash\necho "Install completed"\n')
        install_script.chmod(0o755)
        
        # Create sample file
        (package_dir / 'agent.py').write_text('# Updated agent code')
        
        # Create package archive
        package_path = tempfile.mktemp(suffix='.tar.gz')
        with tarfile.open(package_path, 'w:gz') as tar:
            for item in package_dir.iterdir():
                tar.add(item, arcname=item.name)
        
        # Create signature file
        signature_info = {
            'file_hash': 'test_hash',
            'signature': 'test_signature',
            'signing_method': 'hmac'
        }
        
        signature_path = package_path + '.sig'
        with open(signature_path, 'w') as f:
            json.dump(signature_info, f)
        
        yield package_path
        
        # Cleanup
        shutil.rmtree(package_dir, ignore_errors=True)
        if os.path.exists(package_path):
            os.unlink(package_path)
        if os.path.exists(signature_path):
            os.unlink(signature_path)
    
    def test_init(self, temp_dirs, mock_version_manager):
        """Test UpdateClient initialization."""
        install_dir, backup_dir = temp_dirs
        
        client = UpdateClient(
            update_server_url="https://update.example.com/",
            agent_id="test-agent",
            api_key="test-key",
            install_dir=install_dir,
            backup_dir=backup_dir,
            version_manager=mock_version_manager
        )
        
        assert client.update_server_url == "https://update.example.com"
        assert client.agent_id == "test-agent"
        assert client.api_key == "test-key"
        assert client.install_dir == Path(install_dir)
        assert client.backup_dir == Path(backup_dir)
        assert client.version_manager == mock_version_manager
        assert client.current_status == UpdateStatus.NO_UPDATE
    
    def test_set_progress_callback(self, update_client):
        """Test setting progress callback."""
        callback = Mock()
        update_client.set_progress_callback(callback)
        
        assert update_client.progress_callback == callback
    
    def test_notify_progress(self, update_client):
        """Test progress notification."""
        callback = Mock()
        update_client.set_progress_callback(callback)
        
        update_client._notify_progress(UpdateStatus.DOWNLOADING, 50.0, "Test message")
        
        assert update_client.current_status == UpdateStatus.DOWNLOADING
        callback.assert_called_once_with(UpdateStatus.DOWNLOADING, 50.0, "Test message")
    
    def test_notify_progress_with_exception(self, update_client):
        """Test progress notification with callback exception."""
        callback = Mock(side_effect=Exception("Callback error"))
        update_client.set_progress_callback(callback)
        
        # Should not raise exception
        update_client._notify_progress(UpdateStatus.DOWNLOADING, 50.0, "Test message")
        
        assert update_client.current_status == UpdateStatus.DOWNLOADING
    
    @pytest.mark.asyncio
    async def test_check_for_updates_available(self, update_client, sample_update_info):
        """Test checking for available updates."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=sample_update_info)
        mock_response.raise_for_status = Mock()
        
        with patch.object(update_client, 'session') as mock_session:
            mock_session.get.return_value.__aenter__.return_value = mock_response
            
            result = await update_client.check_for_updates()
            
            assert result == sample_update_info
            assert update_client.current_status == UpdateStatus.AVAILABLE
            assert update_client.update_info == sample_update_info
    
    @pytest.mark.asyncio
    async def test_check_for_updates_none_available(self, update_client):
        """Test checking for updates when none available."""
        mock_response = AsyncMock()
        mock_response.status = 404
        
        with patch.object(update_client, 'session') as mock_session:
            mock_session.get.return_value.__aenter__.return_value = mock_response
            
            result = await update_client.check_for_updates()
            
            assert result is None
            assert update_client.current_status == UpdateStatus.NO_UPDATE
    
    @pytest.mark.asyncio
    async def test_check_for_updates_no_current_version(self, update_client):
        """Test checking for updates when current version unavailable."""
        update_client.version_manager.get_current_version.return_value = None
        
        with patch.object(update_client, 'session'):
            result = await update_client.check_for_updates()
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_check_for_updates_server_error(self, update_client):
        """Test checking for updates with server error."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=Mock(), history=(), status=500
        )
        
        with patch.object(update_client, 'session') as mock_session:
            mock_session.get.return_value.__aenter__.return_value = mock_response
            
            result = await update_client.check_for_updates()
            
            assert result is None
            assert update_client.current_status == UpdateStatus.FAILED
    
    @pytest.mark.asyncio
    async def test_download_update(self, update_client, sample_update_info):
        """Test downloading update package."""
        package_content = b"fake package content"
        signature_content = b"fake signature"
        
        # Mock response for package download
        mock_package_response = AsyncMock()
        mock_package_response.raise_for_status = Mock()
        mock_package_response.content.iter_chunked = AsyncMock(return_value=[package_content])
        
        # Mock response for signature download
        mock_signature_response = AsyncMock()
        mock_signature_response.raise_for_status = Mock()
        mock_signature_response.content.iter_chunked = AsyncMock(return_value=[signature_content])
        
        with patch.object(update_client, 'session') as mock_session:
            mock_session.get.side_effect = [
                mock_package_response.__aenter__.return_value,
                mock_signature_response.__aenter__.return_value
            ]
            mock_session.get.return_value.__aenter__ = AsyncMock(side_effect=[
                mock_package_response, mock_signature_response
            ])
            
            package_path = await update_client.download_update(sample_update_info)
            
            assert package_path is not None
            assert os.path.exists(package_path)
            assert os.path.exists(package_path + '.sig')
            assert update_client.current_status == UpdateStatus.DOWNLOADING
    
    @pytest.mark.asyncio
    async def test_download_update_no_info(self, update_client):
        """Test downloading update without update info."""
        with patch.object(update_client, 'session'):
            result = await update_client.download_update()
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_download_update_download_error(self, update_client, sample_update_info):
        """Test download error handling."""
        mock_response = AsyncMock()
        mock_response.raise_for_status.side_effect = aiohttp.ClientResponseError(
            request_info=Mock(), history=(), status=404
        )
        
        with patch.object(update_client, 'session') as mock_session:
            mock_session.get.return_value.__aenter__.return_value = mock_response
            
            result = await update_client.download_update(sample_update_info)
            
            assert result is None
            assert update_client.current_status == UpdateStatus.FAILED
    
    def test_verify_update_package_valid(self, update_client, sample_package):
        """Test verifying valid update package."""
        # Mock file hash calculation
        with patch('hashlib.sha256') as mock_hash:
            mock_hash.return_value.hexdigest.return_value = 'test_hash'
            
            result = update_client.verify_update_package(sample_package)
        
        assert result is True
        assert update_client.current_status == UpdateStatus.VERIFYING
    
    def test_verify_update_package_missing_file(self, update_client):
        """Test verifying non-existent package."""
        result = update_client.verify_update_package('/nonexistent/package.tar.gz')
        
        assert result is False
    
    def test_verify_update_package_invalid_format(self, update_client):
        """Test verifying invalid package format."""
        # Create invalid package file
        invalid_package = tempfile.mktemp(suffix='.tar.gz')
        with open(invalid_package, 'w') as f:
            f.write("invalid content")
        
        try:
            result = update_client.verify_update_package(invalid_package)
            assert result is False
        finally:
            os.unlink(invalid_package)
    
    def test_verify_update_package_missing_required_files(self, update_client):
        """Test verifying package with missing required files."""
        # Create package without required files
        package_dir = Path(tempfile.mkdtemp())
        package_path = tempfile.mktemp(suffix='.tar.gz')
        
        try:
            # Create empty package
            with tarfile.open(package_path, 'w:gz') as tar:
                pass
            
            result = update_client.verify_update_package(package_path)
            assert result is False
        
        finally:
            shutil.rmtree(package_dir, ignore_errors=True)
            if os.path.exists(package_path):
                os.unlink(package_path)
    
    def test_verify_update_package_hash_mismatch(self, update_client, sample_package):
        """Test verifying package with hash mismatch."""
        # Mock file hash to return different hash
        with patch('hashlib.sha256') as mock_hash:
            mock_hash.return_value.hexdigest.return_value = 'different_hash'
            
            result = update_client.verify_update_package(sample_package)
        
        assert result is False
    
    def test_create_backup(self, update_client, temp_dirs):
        """Test creating backup."""
        install_dir, backup_dir = temp_dirs
        
        # Create some files in install directory
        test_file = Path(install_dir) / 'test_file.txt'
        test_file.write_text('test content')
        
        result = update_client.create_backup()
        
        assert result is True
        
        # Check backup was created
        backups = list(Path(backup_dir).glob('backup_*.tar.gz'))
        assert len(backups) == 1
        
        # Verify backup content
        with tarfile.open(backups[0], 'r:gz') as tar:
            members = tar.getnames()
            assert 'test_file.txt' in members
    
    def test_create_backup_error(self, update_client):
        """Test backup creation error handling."""
        # Make backup directory read-only
        update_client.backup_dir.chmod(0o444)
        
        try:
            result = update_client.create_backup()
            assert result is False
        finally:
            # Restore permissions for cleanup
            update_client.backup_dir.chmod(0o755)
    
    def test_install_update(self, update_client, sample_package, temp_dirs):
        """Test installing update package."""
        install_dir, _ = temp_dirs
        
        with patch.object(update_client, 'create_backup', return_value=True):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value.returncode = 0
                
                result = update_client.install_update(sample_package)
        
        assert result is True
        assert update_client.current_status == UpdateStatus.INSTALLING
        
        # Verify version was saved
        update_client.version_manager.save_version.assert_called_once()
    
    def test_install_update_backup_failed(self, update_client, sample_package):
        """Test install failure when backup fails."""
        with patch.object(update_client, 'create_backup', return_value=False):
            result = update_client.install_update(sample_package)
        
        assert result is False
    
    def test_install_update_version_save_failed(self, update_client, sample_package):
        """Test install failure when version save fails."""
        update_client.version_manager.save_version.return_value = False
        
        with patch.object(update_client, 'create_backup', return_value=True):
            result = update_client.install_update(sample_package)
        
        assert result is False
    
    def test_install_update_script_failed(self, update_client, sample_package):
        """Test install failure when script fails."""
        with patch.object(update_client, 'create_backup', return_value=True):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value.returncode = 1
                mock_run.return_value.stderr = "Script error"
                
                result = update_client.install_update(sample_package)
        
        assert result is False
    
    def test_install_update_script_timeout(self, update_client, sample_package):
        """Test install failure when script times out."""
        with patch.object(update_client, 'create_backup', return_value=True):
            with patch('subprocess.run') as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired('bash', 300)
                
                result = update_client.install_update(sample_package)
        
        assert result is False
    
    def test_schedule_restart(self, update_client, temp_dirs):
        """Test scheduling restart."""
        install_dir, _ = temp_dirs
        
        with patch('subprocess.Popen') as mock_popen:
            result = update_client.schedule_restart(delay_seconds=1)
        
        assert result is True
        mock_popen.assert_called_once()
        
        # Verify restart script was created
        restart_script = Path(install_dir) / 'restart_agent.sh'
        assert restart_script.exists()
        assert restart_script.stat().st_mode & 0o777 == 0o755
    
    def test_schedule_restart_error(self, update_client):
        """Test restart scheduling error."""
        with patch('subprocess.Popen', side_effect=Exception("Popen error")):
            result = update_client.schedule_restart()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_perform_update_success(self, update_client, sample_update_info, sample_package):
        """Test complete update process."""
        with patch.object(update_client, 'check_for_updates', return_value=sample_update_info):
            with patch.object(update_client, 'download_update', return_value=sample_package):
                with patch.object(update_client, 'verify_update_package', return_value=True):
                    with patch.object(update_client, 'install_update', return_value=True):
                        with patch.object(update_client, 'schedule_restart', return_value=True):
                            result = await update_client.perform_update()
        
        assert result is True
        assert update_client.current_status == UpdateStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_perform_update_no_updates(self, update_client):
        """Test update process when no updates available."""
        with patch.object(update_client, 'check_for_updates', return_value=None):
            result = await update_client.perform_update()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_perform_update_download_failed(self, update_client, sample_update_info):
        """Test update process when download fails."""
        with patch.object(update_client, 'check_for_updates', return_value=sample_update_info):
            with patch.object(update_client, 'download_update', return_value=None):
                result = await update_client.perform_update()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_perform_update_verification_failed(self, update_client, sample_update_info, sample_package):
        """Test update process when verification fails."""
        with patch.object(update_client, 'check_for_updates', return_value=sample_update_info):
            with patch.object(update_client, 'download_update', return_value=sample_package):
                with patch.object(update_client, 'verify_update_package', return_value=False):
                    result = await update_client.perform_update()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_perform_update_installation_failed(self, update_client, sample_update_info, sample_package):
        """Test update process when installation fails."""
        with patch.object(update_client, 'check_for_updates', return_value=sample_update_info):
            with patch.object(update_client, 'download_update', return_value=sample_package):
                with patch.object(update_client, 'verify_update_package', return_value=True):
                    with patch.object(update_client, 'install_update', return_value=False):
                        result = await update_client.perform_update()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_perform_update_no_auto_restart(self, update_client, sample_update_info, sample_package):
        """Test update process without auto restart."""
        with patch.object(update_client, 'check_for_updates', return_value=sample_update_info):
            with patch.object(update_client, 'download_update', return_value=sample_package):
                with patch.object(update_client, 'verify_update_package', return_value=True):
                    with patch.object(update_client, 'install_update', return_value=True):
                        with patch.object(update_client, 'schedule_restart') as mock_restart:
                            result = await update_client.perform_update(auto_restart=False)
        
        assert result is True
        mock_restart.assert_not_called()
    
    def test_rollback_update(self, update_client, temp_dirs):
        """Test rolling back update."""
        install_dir, backup_dir = temp_dirs
        
        # Create backup file
        backup_path = Path(backup_dir) / 'backup_20240101_120000.tar.gz'
        with tarfile.open(backup_path, 'w:gz') as tar:
            # Add test file to backup
            test_file = Path(tempfile.mkdtemp()) / 'test_file.txt'
            test_file.write_text('backup content')
            tar.add(test_file, arcname='test_file.txt')
        
        # Create current file in install dir
        current_file = Path(install_dir) / 'current_file.txt'
        current_file.write_text('current content')
        
        result = update_client.rollback_update('backup_20240101_120000.tar.gz')
        
        assert result is True
        
        # Verify rollback
        assert not current_file.exists()  # Current file should be removed
        restored_file = Path(install_dir) / 'test_file.txt'
        assert restored_file.exists()
        assert restored_file.read_text() == 'backup content'
    
    def test_rollback_update_latest_backup(self, update_client, temp_dirs):
        """Test rolling back to latest backup."""
        install_dir, backup_dir = temp_dirs
        
        # Create multiple backup files
        backup1 = Path(backup_dir) / 'backup_20240101_120000.tar.gz'
        backup2 = Path(backup_dir) / 'backup_20240102_120000.tar.gz'
        
        for backup_path in [backup1, backup2]:
            with tarfile.open(backup_path, 'w:gz') as tar:
                pass
        
        # Make backup2 newer
        import time
        time.sleep(0.1)
        backup2.touch()
        
        with patch('tarfile.open') as mock_tar:
            mock_tar.return_value.__enter__.return_value.extractall = Mock()
            
            result = update_client.rollback_update()
        
        assert result is True
        # Should use the newer backup
        mock_tar.assert_called_with(backup2, 'r:gz')
    
    def test_rollback_update_no_backups(self, update_client):
        """Test rollback when no backups exist."""
        result = update_client.rollback_update()
        
        assert result is False
    
    def test_rollback_update_backup_not_found(self, update_client):
        """Test rollback when specified backup not found."""
        result = update_client.rollback_update('nonexistent_backup.tar.gz')
        
        assert result is False
    
    def test_get_system_info(self, update_client):
        """Test getting system information."""
        with patch('platform.system', return_value='Linux'):
            with patch('platform.machine', return_value='x86_64'):
                with patch('platform.python_version', return_value='3.9.0'):
                    info = update_client._get_system_info()
        
        assert info['platform'] == 'linux'
        assert info['architecture'] == 'x86_64'
        assert info['python_version'] == '3.9.0'
    
    def test_get_update_status(self, update_client, sample_update_info):
        """Test getting update status."""
        update_client.update_info = sample_update_info
        update_client.current_status = UpdateStatus.DOWNLOADING
        
        status = update_client.get_update_status()
        
        assert status['status'] == UpdateStatus.DOWNLOADING
        assert status['update_info'] == sample_update_info
        assert 'current_version' in status
        assert 'install_dir' in status
        assert 'backup_dir' in status
    
    def test_cleanup_old_backups(self, update_client, temp_dirs):
        """Test cleaning up old backups."""
        install_dir, backup_dir = temp_dirs
        
        # Create multiple backup files
        backup_files = []
        for i in range(7):
            backup_path = Path(backup_dir) / f'backup_2024010{i}_120000.tar.gz'
            backup_path.write_text(f'backup {i}')
            backup_files.append(backup_path)
            time.sleep(0.01)  # Ensure different modification times
        
        deleted_count = update_client.cleanup_old_backups(keep_count=3)
        
        assert deleted_count == 4
        
        # Check that only 3 most recent backups remain
        remaining_backups = list(Path(backup_dir).glob('backup_*.tar.gz'))
        assert len(remaining_backups) == 3
    
    def test_cleanup_old_backups_error(self, update_client, temp_dirs):
        """Test backup cleanup error handling."""
        install_dir, backup_dir = temp_dirs
        
        # Create backup file and make it read-only
        backup_path = Path(backup_dir) / 'backup_20240101_120000.tar.gz'
        backup_path.write_text('backup content')
        backup_path.chmod(0o444)
        
        # Make parent directory read-only to prevent deletion
        Path(backup_dir).chmod(0o444)
        
        try:
            deleted_count = update_client.cleanup_old_backups(keep_count=0)
            # Should handle error gracefully
            assert deleted_count == 0
        finally:
            # Restore permissions for cleanup
            Path(backup_dir).chmod(0o755)
            backup_path.chmod(0o644)


@pytest.mark.asyncio
class TestUpdateClientIntegration:
    """Integration tests for UpdateClient."""
    
    @pytest.fixture
    def integration_client(self):
        """Create client for integration testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = os.path.join(temp_dir, 'install')
            backup_dir = os.path.join(temp_dir, 'backup')
            
            client = UpdateClient(
                update_server_url="https://update.example.com",
                agent_id="test-agent",
                api_key="test-key",
                install_dir=install_dir,
                backup_dir=backup_dir
            )
            
            yield client
    
    async def test_context_manager(self, integration_client):
        """Test async context manager functionality."""
        async with integration_client as client:
            assert client.session is not None
            assert isinstance(client.session, aiohttp.ClientSession)
        
        # Session should be closed after context
        assert client.session.closed
    
    async def test_full_update_workflow_simulation(self, integration_client):
        """Test simulated full update workflow."""
        # This test simulates the full workflow without actual network calls
        
        update_info = {
            'available': True,
            'version': '1.1.0',
            'download_url': 'https://example.com/package.tar.gz',
            'size': 1000
        }
        
        # Mock all external dependencies
        with patch.object(integration_client, 'check_for_updates', return_value=update_info):
            with patch.object(integration_client, 'download_update', return_value='/tmp/package.tar.gz'):
                with patch.object(integration_client, 'verify_update_package', return_value=True):
                    with patch.object(integration_client, 'install_update', return_value=True):
                        with patch.object(integration_client, 'schedule_restart', return_value=True):
                            
                            # Track progress
                            progress_calls = []
                            def progress_callback(status, progress, message):
                                progress_calls.append((status, progress, message))
                            
                            integration_client.set_progress_callback(progress_callback)
                            
                            # Perform update
                            result = await integration_client.perform_update()
                            
                            assert result is True
                            assert len(progress_calls) > 0
                            assert integration_client.current_status == UpdateStatus.COMPLETED


if __name__ == '__main__':
    pytest.main([__file__])