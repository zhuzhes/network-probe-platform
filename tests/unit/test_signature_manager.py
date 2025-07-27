"""
Unit tests for signature manager.
"""

import pytest
import os
import tempfile
import json
import base64
from unittest.mock import patch, mock_open

from management_platform.updater.signature_manager import SignatureManager


class TestSignatureManager:
    """Test SignatureManager class."""
    
    def setup_method(self):
        """Set up test method."""
        self.temp_dir = tempfile.mkdtemp()
        self.private_key_path = os.path.join(self.temp_dir, "private.pem")
        self.public_key_path = os.path.join(self.temp_dir, "public.pem")
        self.test_file = os.path.join(self.temp_dir, "test_file.txt")
        
        # Create test file
        with open(self.test_file, 'w') as f:
            f.write("This is a test file for signing.")
        
        self.manager = SignatureManager(
            private_key_path=self.private_key_path,
            public_key_path=self.public_key_path,
            hmac_secret="test_secret_key"
        )
    
    def teardown_method(self):
        """Clean up after test method."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_generate_rsa_keypair(self):
        """Test RSA key pair generation."""
        private_pem, public_pem = self.manager.generate_rsa_keypair(2048)
        
        assert isinstance(private_pem, bytes)
        assert isinstance(public_pem, bytes)
        assert b"BEGIN PRIVATE KEY" in private_pem
        assert b"BEGIN PUBLIC KEY" in public_pem
    
    def test_save_and_load_keypair(self):
        """Test saving and loading RSA key pair."""
        # Generate key pair
        private_pem, public_pem = self.manager.generate_rsa_keypair(2048)
        
        # Save key pair
        result = self.manager.save_keypair(
            private_pem, public_pem,
            self.private_key_path, self.public_key_path
        )
        assert result is True
        
        # Check files exist
        assert os.path.exists(self.private_key_path)
        assert os.path.exists(self.public_key_path)
        
        # Check private key permissions
        stat_info = os.stat(self.private_key_path)
        assert oct(stat_info.st_mode)[-3:] == '600'
        
        # Load keys
        assert self.manager.load_private_key() is True
        assert self.manager.load_public_key() is True
    
    def test_calculate_file_hash(self):
        """Test file hash calculation."""
        hash_value = self.manager.calculate_file_hash(self.test_file)
        
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA256 hex digest length
        
        # Test different algorithms
        md5_hash = self.manager.calculate_file_hash(self.test_file, 'md5')
        assert len(md5_hash) == 32  # MD5 hex digest length
    
    def test_calculate_file_hash_nonexistent(self):
        """Test file hash calculation with non-existent file."""
        with pytest.raises(Exception):
            self.manager.calculate_file_hash("nonexistent_file.txt")
    
    def test_sign_and_verify_data_rsa(self):
        """Test RSA data signing and verification."""
        # Generate and load keys
        private_pem, public_pem = self.manager.generate_rsa_keypair(2048)
        self.manager.save_keypair(
            private_pem, public_pem,
            self.private_key_path, self.public_key_path
        )
        self.manager.load_private_key()
        self.manager.load_public_key()
        
        # Test data
        test_data = b"This is test data for signing"
        
        # Sign data
        signature = self.manager.sign_data_rsa(test_data)
        assert isinstance(signature, bytes)
        
        # Verify signature
        assert self.manager.verify_signature_rsa(test_data, signature) is True
        
        # Verify with wrong data
        wrong_data = b"This is wrong data"
        assert self.manager.verify_signature_rsa(wrong_data, signature) is False
    
    def test_sign_and_verify_data_hmac(self):
        """Test HMAC data signing and verification."""
        test_data = b"This is test data for HMAC signing"
        
        # Sign data
        signature = self.manager.sign_data_hmac(test_data)
        assert isinstance(signature, str)
        
        # Verify signature
        assert self.manager.verify_signature_hmac(test_data, signature) is True
        
        # Verify with wrong data
        wrong_data = b"This is wrong data"
        assert self.manager.verify_signature_hmac(wrong_data, signature) is False
        
        # Test with custom secret
        custom_signature = self.manager.sign_data_hmac(test_data, "custom_secret")
        assert self.manager.verify_signature_hmac(
            test_data, custom_signature, "custom_secret"
        ) is True
    
    def test_sign_file_rsa(self):
        """Test RSA file signing."""
        # Generate and load keys
        private_pem, public_pem = self.manager.generate_rsa_keypair(2048)
        self.manager.save_keypair(
            private_pem, public_pem,
            self.private_key_path, self.public_key_path
        )
        
        # Sign file
        signature_info = self.manager.sign_file(self.test_file, 'rsa')
        
        assert isinstance(signature_info, dict)
        assert signature_info['file_path'] == self.test_file
        assert signature_info['signing_method'] == 'rsa'
        assert 'signature' in signature_info
        assert 'file_hash' in signature_info
        assert 'file_size' in signature_info
    
    def test_sign_file_hmac(self):
        """Test HMAC file signing."""
        signature_info = self.manager.sign_file(self.test_file, 'hmac')
        
        assert isinstance(signature_info, dict)
        assert signature_info['file_path'] == self.test_file
        assert signature_info['signing_method'] == 'hmac'
        assert 'signature' in signature_info
        assert 'file_hash' in signature_info
        assert 'file_size' in signature_info
    
    def test_sign_file_nonexistent(self):
        """Test signing non-existent file."""
        with pytest.raises(FileNotFoundError):
            self.manager.sign_file("nonexistent_file.txt")
    
    def test_sign_file_invalid_method(self):
        """Test signing with invalid method."""
        with pytest.raises(ValueError):
            self.manager.sign_file(self.test_file, 'invalid_method')
    
    def test_verify_file_signature_rsa(self):
        """Test RSA file signature verification."""
        # Generate and load keys
        private_pem, public_pem = self.manager.generate_rsa_keypair(2048)
        self.manager.save_keypair(
            private_pem, public_pem,
            self.private_key_path, self.public_key_path
        )
        
        # Sign file
        signature_info = self.manager.sign_file(self.test_file, 'rsa')
        
        # Verify signature
        assert self.manager.verify_file_signature(self.test_file, signature_info) is True
        
        # Modify file and verify (should fail)
        with open(self.test_file, 'a') as f:
            f.write(" modified")
        
        assert self.manager.verify_file_signature(self.test_file, signature_info) is False
    
    def test_verify_file_signature_hmac(self):
        """Test HMAC file signature verification."""
        # Sign file
        signature_info = self.manager.sign_file(self.test_file, 'hmac')
        
        # Verify signature
        assert self.manager.verify_file_signature(self.test_file, signature_info) is True
        
        # Modify file and verify (should fail)
        with open(self.test_file, 'a') as f:
            f.write(" modified")
        
        assert self.manager.verify_file_signature(self.test_file, signature_info) is False
    
    def test_verify_file_signature_nonexistent(self):
        """Test verifying signature of non-existent file."""
        signature_info = self.manager.sign_file(self.test_file, 'hmac')
        
        # Remove file
        os.remove(self.test_file)
        
        # Verify should fail
        assert self.manager.verify_file_signature(self.test_file, signature_info) is False
    
    def test_create_signature_manifest(self):
        """Test signature manifest creation."""
        # Create multiple signature infos
        signatures = [
            self.manager.sign_file(self.test_file, 'hmac'),
        ]
        
        # Create another test file
        test_file2 = os.path.join(self.temp_dir, "test_file2.txt")
        with open(test_file2, 'w') as f:
            f.write("Another test file")
        
        signatures.append(self.manager.sign_file(test_file2, 'hmac'))
        
        # Create manifest
        manifest = self.manager.create_signature_manifest(signatures)
        
        assert isinstance(manifest, dict)
        assert manifest['version'] == '1.0'
        assert manifest['total_files'] == 2
        assert 'created_at' in manifest
        assert 'signatures' in manifest
        assert 'manifest_signature' in manifest
    
    def test_verify_signature_manifest(self):
        """Test signature manifest verification."""
        # Create signatures
        signatures = [self.manager.sign_file(self.test_file, 'hmac')]
        
        # Create and verify manifest
        manifest = self.manager.create_signature_manifest(signatures)
        assert self.manager.verify_signature_manifest(manifest) is True
        
        # Tamper with manifest
        manifest['total_files'] = 999
        assert self.manager.verify_signature_manifest(manifest) is False
    
    def test_verify_signature_manifest_no_signature(self):
        """Test verifying manifest without signature."""
        manifest = {
            'version': '1.0',
            'created_at': 1234567890,
            'signatures': [],
            'total_files': 0
        }
        
        assert self.manager.verify_signature_manifest(manifest) is False
    
    def test_rsa_operations_without_keys(self):
        """Test RSA operations without loaded keys."""
        with pytest.raises(ValueError):
            self.manager.sign_data_rsa(b"test data")
        
        with pytest.raises(ValueError):
            self.manager.verify_signature_rsa(b"test data", b"signature")
    
    def test_hmac_operations_without_secret(self):
        """Test HMAC operations without secret."""
        manager = SignatureManager()  # No HMAC secret
        
        with pytest.raises(ValueError):
            manager.sign_data_hmac(b"test data")
    
    @patch('builtins.open', side_effect=IOError("File error"))
    def test_save_keypair_error(self, mock_file):
        """Test save_keypair with file error."""
        private_pem, public_pem = self.manager.generate_rsa_keypair(2048)
        result = self.manager.save_keypair(
            private_pem, public_pem,
            self.private_key_path, self.public_key_path
        )
        assert result is False
    
    def test_load_private_key_nonexistent(self):
        """Test loading non-existent private key."""
        manager = SignatureManager(private_key_path="nonexistent.pem")
        assert manager.load_private_key() is False
    
    def test_load_public_key_nonexistent(self):
        """Test loading non-existent public key."""
        manager = SignatureManager(public_key_path="nonexistent.pem")
        assert manager.load_public_key() is False
    
    @patch('builtins.open', mock_open(read_data=b'invalid key data'))
    def test_load_invalid_private_key(self):
        """Test loading invalid private key."""
        with patch('os.path.exists', return_value=True):
            assert self.manager.load_private_key() is False
    
    @patch('builtins.open', mock_open(read_data=b'invalid key data'))
    def test_load_invalid_public_key(self):
        """Test loading invalid public key."""
        with patch('os.path.exists', return_value=True):
            assert self.manager.load_public_key() is False