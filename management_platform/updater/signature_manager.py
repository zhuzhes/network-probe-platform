"""
Signature manager for update package signing and verification.
Provides cryptographic signing capabilities for secure OTA updates.
"""

import os
import hashlib
import hmac
import base64
import json
import time
from typing import Dict, Any, Optional, Tuple
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key
from cryptography.exceptions import InvalidSignature
import logging

logger = logging.getLogger(__name__)


class SignatureManager:
    """
    Manages cryptographic signatures for update packages.
    Supports both RSA and HMAC signing methods.
    """
    
    def __init__(self, private_key_path: Optional[str] = None, 
                 public_key_path: Optional[str] = None,
                 hmac_secret: Optional[str] = None):
        """
        Initialize signature manager.
        
        Args:
            private_key_path: Path to RSA private key file
            public_key_path: Path to RSA public key file
            hmac_secret: HMAC secret key for symmetric signing
        """
        self.private_key_path = private_key_path
        self.public_key_path = public_key_path
        self.hmac_secret = hmac_secret
        self._private_key = None
        self._public_key = None
    
    def generate_rsa_keypair(self, key_size: int = 2048) -> Tuple[bytes, bytes]:
        """
        Generate RSA key pair for signing.
        
        Args:
            key_size: RSA key size in bits
            
        Returns:
            Tuple of (private_key_pem, public_key_pem)
        """
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size
        )
        
        # Get public key
        public_key = private_key.public_key()
        
        # Serialize keys to PEM format
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        logger.info(f"Generated RSA key pair with {key_size} bits")
        return private_pem, public_pem
    
    def save_keypair(self, private_pem: bytes, public_pem: bytes,
                    private_path: str, public_path: str) -> bool:
        """
        Save RSA key pair to files.
        
        Args:
            private_pem: Private key in PEM format
            public_pem: Public key in PEM format
            private_path: Path to save private key
            public_path: Path to save public key
            
        Returns:
            True if saved successfully
        """
        try:
            # Create directories if they don't exist
            os.makedirs(os.path.dirname(private_path) or '.', exist_ok=True)
            os.makedirs(os.path.dirname(public_path) or '.', exist_ok=True)
            
            # Save private key with restricted permissions
            with open(private_path, 'wb') as f:
                f.write(private_pem)
            os.chmod(private_path, 0o600)  # Read/write for owner only
            
            # Save public key
            with open(public_path, 'wb') as f:
                f.write(public_pem)
            
            logger.info(f"Saved key pair to {private_path} and {public_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving key pair: {e}")
            return False
    
    def load_private_key(self, password: Optional[bytes] = None) -> bool:
        """
        Load RSA private key from file.
        
        Args:
            password: Optional password for encrypted key
            
        Returns:
            True if loaded successfully
        """
        if not self.private_key_path or not os.path.exists(self.private_key_path):
            logger.error(f"Private key file not found: {self.private_key_path}")
            return False
        
        try:
            with open(self.private_key_path, 'rb') as f:
                key_data = f.read()
            
            self._private_key = load_pem_private_key(key_data, password)
            logger.info("Private key loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Error loading private key: {e}")
            return False
    
    def load_public_key(self) -> bool:
        """
        Load RSA public key from file.
        
        Returns:
            True if loaded successfully
        """
        if not self.public_key_path or not os.path.exists(self.public_key_path):
            logger.error(f"Public key file not found: {self.public_key_path}")
            return False
        
        try:
            with open(self.public_key_path, 'rb') as f:
                key_data = f.read()
            
            self._public_key = load_pem_public_key(key_data)
            logger.info("Public key loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Error loading public key: {e}")
            return False
    
    def calculate_file_hash(self, file_path: str, algorithm: str = 'sha256') -> str:
        """
        Calculate hash of a file.
        
        Args:
            file_path: Path to file
            algorithm: Hash algorithm (sha256, sha512, md5)
            
        Returns:
            Hex digest of file hash
        """
        hash_func = getattr(hashlib, algorithm)()
        
        try:
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_func.update(chunk)
            
            return hash_func.hexdigest()
        except Exception as e:
            logger.error(f"Error calculating file hash: {e}")
            raise
    
    def sign_data_rsa(self, data: bytes) -> bytes:
        """
        Sign data using RSA private key.
        
        Args:
            data: Data to sign
            
        Returns:
            Signature bytes
        """
        if not self._private_key:
            if not self.load_private_key():
                raise ValueError("Private key not available")
        
        try:
            signature = self._private_key.sign(
                data,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return signature
        except Exception as e:
            logger.error(f"Error signing data: {e}")
            raise
    
    def verify_signature_rsa(self, data: bytes, signature: bytes) -> bool:
        """
        Verify RSA signature.
        
        Args:
            data: Original data
            signature: Signature to verify
            
        Returns:
            True if signature is valid
        """
        if not self._public_key:
            if not self.load_public_key():
                raise ValueError("Public key not available")
        
        try:
            self._public_key.verify(
                signature,
                data,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return True
        except InvalidSignature:
            return False
        except Exception as e:
            logger.error(f"Error verifying signature: {e}")
            raise
    
    def sign_data_hmac(self, data: bytes, secret: Optional[str] = None) -> str:
        """
        Sign data using HMAC.
        
        Args:
            data: Data to sign
            secret: HMAC secret (uses instance secret if not provided)
            
        Returns:
            Base64 encoded HMAC signature
        """
        secret_key = secret or self.hmac_secret
        if not secret_key:
            raise ValueError("HMAC secret not available")
        
        signature = hmac.new(
            secret_key.encode('utf-8'),
            data,
            hashlib.sha256
        ).digest()
        
        return base64.b64encode(signature).decode('utf-8')
    
    def verify_signature_hmac(self, data: bytes, signature: str, 
                             secret: Optional[str] = None) -> bool:
        """
        Verify HMAC signature.
        
        Args:
            data: Original data
            signature: Base64 encoded signature to verify
            secret: HMAC secret (uses instance secret if not provided)
            
        Returns:
            True if signature is valid
        """
        try:
            expected_signature = self.sign_data_hmac(data, secret)
            return hmac.compare_digest(signature, expected_signature)
        except Exception as e:
            logger.error(f"Error verifying HMAC signature: {e}")
            return False
    
    def sign_file(self, file_path: str, method: str = 'rsa') -> Dict[str, Any]:
        """
        Sign a file and return signature information.
        
        Args:
            file_path: Path to file to sign
            method: Signing method ('rsa' or 'hmac')
            
        Returns:
            Dictionary containing signature information
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Calculate file hash
        file_hash = self.calculate_file_hash(file_path)
        file_size = os.path.getsize(file_path)
        
        # Read file data
        with open(file_path, 'rb') as f:
            file_data = f.read()
        
        # Create signature info
        signature_info = {
            'file_path': file_path,
            'file_size': file_size,
            'file_hash': file_hash,
            'hash_algorithm': 'sha256',
            'signing_method': method,
            'timestamp': int(os.path.getmtime(file_path))
        }
        
        # Sign based on method
        if method == 'rsa':
            signature = self.sign_data_rsa(file_data)
            signature_info['signature'] = base64.b64encode(signature).decode('utf-8')
        elif method == 'hmac':
            signature_info['signature'] = self.sign_data_hmac(file_data)
        else:
            raise ValueError(f"Unknown signing method: {method}")
        
        logger.info(f"Signed file {file_path} using {method}")
        return signature_info
    
    def verify_file_signature(self, file_path: str, 
                             signature_info: Dict[str, Any]) -> bool:
        """
        Verify file signature.
        
        Args:
            file_path: Path to file to verify
            signature_info: Signature information dictionary
            
        Returns:
            True if signature is valid
        """
        if not os.path.exists(file_path):
            logger.error(f"File not found: {file_path}")
            return False
        
        try:
            # Verify file hash
            current_hash = self.calculate_file_hash(file_path)
            if current_hash != signature_info['file_hash']:
                logger.error("File hash mismatch")
                return False
            
            # Verify file size
            current_size = os.path.getsize(file_path)
            if current_size != signature_info['file_size']:
                logger.error("File size mismatch")
                return False
            
            # Read file data
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            # Verify signature based on method
            method = signature_info['signing_method']
            signature = signature_info['signature']
            
            if method == 'rsa':
                signature_bytes = base64.b64decode(signature)
                return self.verify_signature_rsa(file_data, signature_bytes)
            elif method == 'hmac':
                return self.verify_signature_hmac(file_data, signature)
            else:
                logger.error(f"Unknown signing method: {method}")
                return False
        
        except Exception as e:
            logger.error(f"Error verifying file signature: {e}")
            return False
    
    def create_signature_manifest(self, signatures: list) -> Dict[str, Any]:
        """
        Create a signature manifest for multiple files.
        
        Args:
            signatures: List of signature information dictionaries
            
        Returns:
            Signature manifest dictionary
        """
        manifest = {
            'version': '1.0',
            'created_at': int(time.time()),
            'signatures': signatures,
            'total_files': len(signatures)
        }
        
        # Sign the manifest itself
        manifest_data = json.dumps(manifest, sort_keys=True).encode('utf-8')
        if self.hmac_secret:
            manifest['manifest_signature'] = self.sign_data_hmac(manifest_data)
        
        return manifest
    
    def verify_signature_manifest(self, manifest: Dict[str, Any]) -> bool:
        """
        Verify signature manifest.
        
        Args:
            manifest: Signature manifest dictionary
            
        Returns:
            True if manifest is valid
        """
        try:
            # Extract manifest signature
            manifest_signature = manifest.pop('manifest_signature', None)
            if not manifest_signature:
                logger.error("Manifest signature not found")
                return False
            
            # Verify manifest signature
            manifest_data = json.dumps(manifest, sort_keys=True).encode('utf-8')
            if not self.verify_signature_hmac(manifest_data, manifest_signature):
                logger.error("Manifest signature verification failed")
                return False
            
            # Restore manifest signature
            manifest['manifest_signature'] = manifest_signature
            
            logger.info("Signature manifest verified successfully")
            return True
        
        except Exception as e:
            logger.error(f"Error verifying signature manifest: {e}")
            return False