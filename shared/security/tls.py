"""TLS配置和证书管理"""

import os
import ssl
import secrets
import hashlib
import ipaddress
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption
import logging

logger = logging.getLogger(__name__)


class TLSConfig:
    """TLS配置管理"""
    
    def __init__(self, cert_dir: str = "certs"):
        self.cert_dir = Path(cert_dir)
        self.cert_dir.mkdir(exist_ok=True)
        
        # 证书文件路径
        self.ca_cert_path = self.cert_dir / "ca.crt"
        self.ca_key_path = self.cert_dir / "ca.key"
        self.server_cert_path = self.cert_dir / "server.crt"
        self.server_key_path = self.cert_dir / "server.key"
        self.client_cert_path = self.cert_dir / "client.crt"
        self.client_key_path = self.cert_dir / "client.key"
        
        # 密钥轮换配置
        self.key_rotation_interval = timedelta(days=30)
        self.cert_validity_days = 365
    
    def generate_private_key(self, key_size: int = 2048) -> rsa.RSAPrivateKey:
        """生成RSA私钥"""
        return rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size,
        )
    
    def create_ca_certificate(self, 
                            subject_name: str = "Network Probe Platform CA",
                            validity_days: int = 3650) -> Tuple[x509.Certificate, rsa.RSAPrivateKey]:
        """创建CA证书"""
        # 生成CA私钥
        ca_key = self.generate_private_key()
        
        # 创建CA证书
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Beijing"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Beijing"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Network Probe Platform"),
            x509.NameAttribute(NameOID.COMMON_NAME, subject_name),
        ])
        
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            ca_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=validity_days)
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]),
            critical=False,
        ).add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        ).add_extension(
            x509.KeyUsage(
                key_cert_sign=True,
                crl_sign=True,
                digital_signature=False,
                key_encipherment=False,
                key_agreement=False,
                data_encipherment=False,
                content_commitment=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        ).sign(ca_key, hashes.SHA256())
        
        return cert, ca_key
    
    def create_server_certificate(self, 
                                ca_cert: x509.Certificate,
                                ca_key: rsa.RSAPrivateKey,
                                server_name: str = "localhost",
                                validity_days: int = 365) -> Tuple[x509.Certificate, rsa.RSAPrivateKey]:
        """创建服务器证书"""
        # 生成服务器私钥
        server_key = self.generate_private_key()
        
        # 创建服务器证书
        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Beijing"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Beijing"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Network Probe Platform"),
            x509.NameAttribute(NameOID.COMMON_NAME, server_name),
        ])
        
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            ca_cert.subject
        ).public_key(
            server_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=validity_days)
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.DNSName(server_name),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
            ]),
            critical=False,
        ).add_extension(
            x509.KeyUsage(
                key_cert_sign=False,
                crl_sign=False,
                digital_signature=True,
                key_encipherment=True,
                key_agreement=False,
                data_encipherment=False,
                content_commitment=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        ).add_extension(
            x509.ExtendedKeyUsage([
                x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
            ]),
            critical=True,
        ).sign(ca_key, hashes.SHA256())
        
        return cert, server_key
    
    def create_client_certificate(self,
                                ca_cert: x509.Certificate,
                                ca_key: rsa.RSAPrivateKey,
                                client_name: str,
                                validity_days: int = 365) -> Tuple[x509.Certificate, rsa.RSAPrivateKey]:
        """创建客户端证书"""
        # 生成客户端私钥
        client_key = self.generate_private_key()
        
        # 创建客户端证书
        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Beijing"),
            x509.NameAttribute(NameOID.LOCALITY_NAME, "Beijing"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Network Probe Platform"),
            x509.NameAttribute(NameOID.COMMON_NAME, client_name),
        ])
        
        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            ca_cert.subject
        ).public_key(
            client_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=validity_days)
        ).add_extension(
            x509.KeyUsage(
                key_cert_sign=False,
                crl_sign=False,
                digital_signature=True,
                key_encipherment=True,
                key_agreement=False,
                data_encipherment=False,
                content_commitment=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        ).add_extension(
            x509.ExtendedKeyUsage([
                x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
            ]),
            critical=True,
        ).sign(ca_key, hashes.SHA256())
        
        return cert, client_key
    
    def save_certificate(self, cert: x509.Certificate, path: Path) -> None:
        """保存证书到文件"""
        with open(path, "wb") as f:
            f.write(cert.public_bytes(Encoding.PEM))
    
    def save_private_key(self, key: rsa.RSAPrivateKey, path: Path, password: Optional[bytes] = None) -> None:
        """保存私钥到文件"""
        encryption = NoEncryption() if password is None else serialization.BestAvailableEncryption(password)
        
        with open(path, "wb") as f:
            f.write(key.private_bytes(
                encoding=Encoding.PEM,
                format=PrivateFormat.PKCS8,
                encryption_algorithm=encryption
            ))
    
    def load_certificate(self, path: Path) -> x509.Certificate:
        """从文件加载证书"""
        with open(path, "rb") as f:
            return x509.load_pem_x509_certificate(f.read())
    
    def load_private_key(self, path: Path, password: Optional[bytes] = None) -> rsa.RSAPrivateKey:
        """从文件加载私钥"""
        with open(path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=password)
    
    def initialize_certificates(self, force_recreate: bool = False) -> None:
        """初始化证书"""
        # 检查是否需要创建或重新创建证书
        if force_recreate or not all([
            self.ca_cert_path.exists(),
            self.ca_key_path.exists(),
            self.server_cert_path.exists(),
            self.server_key_path.exists()
        ]):
            logger.info("Creating new certificates...")
            
            # 创建CA证书
            ca_cert, ca_key = self.create_ca_certificate()
            self.save_certificate(ca_cert, self.ca_cert_path)
            self.save_private_key(ca_key, self.ca_key_path)
            
            # 创建服务器证书
            server_cert, server_key = self.create_server_certificate(ca_cert, ca_key)
            self.save_certificate(server_cert, self.server_cert_path)
            self.save_private_key(server_key, self.server_key_path)
            
            logger.info("Certificates created successfully")
        else:
            logger.info("Certificates already exist")
    
    def create_agent_certificate(self, agent_id: str) -> Tuple[str, str]:
        """为代理创建客户端证书"""
        # 加载CA证书和私钥
        ca_cert = self.load_certificate(self.ca_cert_path)
        ca_key = self.load_private_key(self.ca_key_path)
        
        # 创建代理证书
        client_cert, client_key = self.create_client_certificate(
            ca_cert, ca_key, f"agent-{agent_id}"
        )
        
        # 返回PEM格式的证书和私钥
        cert_pem = client_cert.public_bytes(Encoding.PEM).decode('utf-8')
        key_pem = client_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption()
        ).decode('utf-8')
        
        return cert_pem, key_pem
    
    def verify_certificate(self, cert_path: Path) -> bool:
        """验证证书有效性"""
        try:
            cert = self.load_certificate(cert_path)
            
            # 检查证书是否过期
            now = datetime.utcnow()
            if now < cert.not_valid_before or now > cert.not_valid_after:
                return False
            
            # 简化验证：只检查证书是否能正确加载和时间有效性
            # 在实际生产环境中，这里应该进行完整的证书链验证
            return True
                
        except Exception as e:
            logger.error(f"Certificate verification failed: {e}")
            return False
    
    def get_ssl_context(self, is_server: bool = True) -> ssl.SSLContext:
        """获取SSL上下文"""
        if is_server:
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            context.load_cert_chain(self.server_cert_path, self.server_key_path)
            context.load_verify_locations(self.ca_cert_path)
            context.verify_mode = ssl.CERT_REQUIRED
        else:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            context.load_cert_chain(self.client_cert_path, self.client_key_path)
            context.load_verify_locations(self.ca_cert_path)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_REQUIRED
        
        # 设置安全的TLS版本和密码套件
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
        
        return context
    
    def should_rotate_keys(self) -> bool:
        """检查是否需要轮换密钥"""
        try:
            cert = self.load_certificate(self.server_cert_path)
            # 如果证书在30天内过期，则需要轮换
            expiry_threshold = datetime.utcnow() + self.key_rotation_interval
            return cert.not_valid_after <= expiry_threshold
        except Exception:
            return True
    
    def rotate_keys(self) -> None:
        """轮换密钥和证书"""
        logger.info("Starting key rotation...")
        
        # 备份旧证书
        backup_dir = self.cert_dir / "backup" / datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        for cert_file in [self.ca_cert_path, self.ca_key_path, 
                         self.server_cert_path, self.server_key_path]:
            if cert_file.exists():
                backup_file = backup_dir / cert_file.name
                cert_file.rename(backup_file)
        
        # 重新创建证书
        self.initialize_certificates(force_recreate=True)
        
        logger.info("Key rotation completed")


class KeyRotationManager:
    """密钥轮换管理器"""
    
    def __init__(self, tls_config: TLSConfig):
        self.tls_config = tls_config
        self.rotation_secrets: Dict[str, str] = {}
    
    def generate_rotation_secret(self) -> str:
        """生成轮换密钥"""
        return secrets.token_urlsafe(32)
    
    def schedule_key_rotation(self) -> None:
        """调度密钥轮换"""
        if self.tls_config.should_rotate_keys():
            self.tls_config.rotate_keys()
    
    def get_current_key_hash(self) -> str:
        """获取当前密钥哈希"""
        try:
            with open(self.tls_config.server_key_path, 'rb') as f:
                key_data = f.read()
            return hashlib.sha256(key_data).hexdigest()
        except Exception:
            return ""


# 全局TLS配置实例
tls_config = TLSConfig()
key_rotation_manager = KeyRotationManager(tls_config)