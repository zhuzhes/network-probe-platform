"""TLS安全配置测试"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import ssl

from shared.security.tls import TLSConfig, KeyRotationManager
from cryptography import x509
from cryptography.hazmat.primitives import serialization


class TestTLSConfig:
    """TLS配置测试"""
    
    @pytest.fixture
    def temp_cert_dir(self):
        """临时证书目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def tls_config(self, temp_cert_dir):
        """TLS配置实例"""
        return TLSConfig(cert_dir=temp_cert_dir)
    
    def test_generate_private_key(self, tls_config):
        """测试生成私钥"""
        key = tls_config.generate_private_key()
        assert key is not None
        assert key.key_size == 2048
    
    def test_create_ca_certificate(self, tls_config):
        """测试创建CA证书"""
        cert, key = tls_config.create_ca_certificate()
        
        # 验证证书基本信息
        assert cert is not None
        assert key is not None
        assert cert.subject == cert.issuer  # 自签名证书
        
        # 验证证书扩展
        basic_constraints = cert.extensions.get_extension_for_oid(
            x509.oid.ExtensionOID.BASIC_CONSTRAINTS
        ).value
        assert basic_constraints.ca is True
        
        # 验证密钥用途
        key_usage = cert.extensions.get_extension_for_oid(
            x509.oid.ExtensionOID.KEY_USAGE
        ).value
        assert key_usage.key_cert_sign is True
        assert key_usage.crl_sign is True
    
    def test_create_server_certificate(self, tls_config):
        """测试创建服务器证书"""
        # 先创建CA证书
        ca_cert, ca_key = tls_config.create_ca_certificate()
        
        # 创建服务器证书
        server_cert, server_key = tls_config.create_server_certificate(ca_cert, ca_key)
        
        # 验证证书基本信息
        assert server_cert is not None
        assert server_key is not None
        assert server_cert.issuer == ca_cert.subject
        
        # 验证扩展密钥用途
        ext_key_usage = server_cert.extensions.get_extension_for_oid(
            x509.oid.ExtensionOID.EXTENDED_KEY_USAGE
        ).value
        assert x509.oid.ExtendedKeyUsageOID.SERVER_AUTH in ext_key_usage
        
        # 验证主题备用名称
        san = server_cert.extensions.get_extension_for_oid(
            x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
        ).value
        dns_names = [name.value for name in san if isinstance(name, x509.DNSName)]
        assert "localhost" in dns_names
    
    def test_create_client_certificate(self, tls_config):
        """测试创建客户端证书"""
        # 先创建CA证书
        ca_cert, ca_key = tls_config.create_ca_certificate()
        
        # 创建客户端证书
        client_cert, client_key = tls_config.create_client_certificate(
            ca_cert, ca_key, "test-client"
        )
        
        # 验证证书基本信息
        assert client_cert is not None
        assert client_key is not None
        assert client_cert.issuer == ca_cert.subject
        
        # 验证扩展密钥用途
        ext_key_usage = client_cert.extensions.get_extension_for_oid(
            x509.oid.ExtensionOID.EXTENDED_KEY_USAGE
        ).value
        assert x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH in ext_key_usage
        
        # 验证通用名称
        common_name = None
        for attribute in client_cert.subject:
            if attribute.oid == x509.oid.NameOID.COMMON_NAME:
                common_name = attribute.value
                break
        assert common_name == "test-client"
    
    def test_save_and_load_certificate(self, tls_config):
        """测试保存和加载证书"""
        # 创建证书
        cert, key = tls_config.create_ca_certificate()
        
        # 保存证书
        cert_path = tls_config.cert_dir / "test.crt"
        tls_config.save_certificate(cert, cert_path)
        
        # 加载证书
        loaded_cert = tls_config.load_certificate(cert_path)
        
        # 验证证书内容相同
        assert cert.public_bytes(serialization.Encoding.PEM) == \
               loaded_cert.public_bytes(serialization.Encoding.PEM)
    
    def test_save_and_load_private_key(self, tls_config):
        """测试保存和加载私钥"""
        # 生成私钥
        key = tls_config.generate_private_key()
        
        # 保存私钥
        key_path = tls_config.cert_dir / "test.key"
        tls_config.save_private_key(key, key_path)
        
        # 加载私钥
        loaded_key = tls_config.load_private_key(key_path)
        
        # 验证私钥内容相同
        assert key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ) == loaded_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
    
    def test_initialize_certificates(self, tls_config):
        """测试初始化证书"""
        # 初始化证书
        tls_config.initialize_certificates()
        
        # 验证证书文件存在
        assert tls_config.ca_cert_path.exists()
        assert tls_config.ca_key_path.exists()
        assert tls_config.server_cert_path.exists()
        assert tls_config.server_key_path.exists()
        
        # 验证证书有效性
        assert tls_config.verify_certificate(tls_config.ca_cert_path)
        assert tls_config.verify_certificate(tls_config.server_cert_path)
    
    def test_create_agent_certificate(self, tls_config):
        """测试创建代理证书"""
        # 先初始化CA证书
        tls_config.initialize_certificates()
        
        # 创建代理证书
        cert_pem, key_pem = tls_config.create_agent_certificate("test-agent-001")
        
        # 验证返回的是PEM格式
        assert cert_pem.startswith("-----BEGIN CERTIFICATE-----")
        assert cert_pem.endswith("-----END CERTIFICATE-----\n")
        assert key_pem.startswith("-----BEGIN PRIVATE KEY-----")
        assert key_pem.endswith("-----END PRIVATE KEY-----\n")
        
        # 验证证书可以解析
        cert = x509.load_pem_x509_certificate(cert_pem.encode('utf-8'))
        key = serialization.load_pem_private_key(key_pem.encode('utf-8'), password=None)
        
        assert cert is not None
        assert key is not None
    
    def test_verify_certificate_valid(self, tls_config):
        """测试验证有效证书"""
        tls_config.initialize_certificates()
        
        # 验证CA证书
        assert tls_config.verify_certificate(tls_config.ca_cert_path) is True
        
        # 验证服务器证书
        assert tls_config.verify_certificate(tls_config.server_cert_path) is True
    
    def test_verify_certificate_invalid(self, tls_config):
        """测试验证无效证书"""
        # 创建一个过期的证书
        ca_cert, ca_key = tls_config.create_ca_certificate()
        
        # 创建一个已过期的服务器证书
        from cryptography.hazmat.primitives import hashes
        from cryptography.x509.oid import NameOID
        
        server_key = tls_config.generate_private_key()
        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "expired-server"),
        ])
        
        # 创建过期证书（有效期为过去的时间）
        expired_cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            ca_cert.subject
        ).public_key(
            server_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow() - timedelta(days=2)
        ).not_valid_after(
            datetime.utcnow() - timedelta(days=1)  # 昨天过期
        ).sign(ca_key, hashes.SHA256())
        
        # 保存过期证书
        expired_cert_path = tls_config.cert_dir / "expired.crt"
        tls_config.save_certificate(expired_cert, expired_cert_path)
        
        # 验证应该失败
        assert tls_config.verify_certificate(expired_cert_path) is False
    
    def test_get_ssl_context_server(self, tls_config):
        """测试获取服务器SSL上下文"""
        tls_config.initialize_certificates()
        
        context = tls_config.get_ssl_context(is_server=True)
        
        assert isinstance(context, ssl.SSLContext)
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.minimum_version == ssl.TLSVersion.TLSv1_2
    
    def test_get_ssl_context_client(self, tls_config):
        """测试获取客户端SSL上下文"""
        tls_config.initialize_certificates()
        
        # 创建客户端证书
        ca_cert = tls_config.load_certificate(tls_config.ca_cert_path)
        ca_key = tls_config.load_private_key(tls_config.ca_key_path)
        client_cert, client_key = tls_config.create_client_certificate(
            ca_cert, ca_key, "test-client"
        )
        tls_config.save_certificate(client_cert, tls_config.client_cert_path)
        tls_config.save_private_key(client_key, tls_config.client_key_path)
        
        context = tls_config.get_ssl_context(is_server=False)
        
        assert isinstance(context, ssl.SSLContext)
        assert context.verify_mode == ssl.CERT_REQUIRED
        assert context.check_hostname is False
        assert context.minimum_version == ssl.TLSVersion.TLSv1_2
    
    def test_should_rotate_keys_false(self, tls_config):
        """测试密钥不需要轮换"""
        tls_config.initialize_certificates()
        
        # 新创建的证书不需要轮换
        assert tls_config.should_rotate_keys() is False
    
    def test_should_rotate_keys_true(self, tls_config):
        """测试密钥需要轮换"""
        # 创建一个即将过期的证书
        ca_cert, ca_key = tls_config.create_ca_certificate()
        
        # 创建一个即将过期的服务器证书（29天后过期）
        from cryptography.hazmat.primitives import hashes
        from cryptography.x509.oid import NameOID
        
        server_key = tls_config.generate_private_key()
        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "expiring-server"),
        ])
        
        expiring_cert = x509.CertificateBuilder().subject_name(
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
            datetime.utcnow() + timedelta(days=29)  # 29天后过期
        ).sign(ca_key, hashes.SHA256())
        
        # 保存证书
        tls_config.save_certificate(ca_cert, tls_config.ca_cert_path)
        tls_config.save_private_key(ca_key, tls_config.ca_key_path)
        tls_config.save_certificate(expiring_cert, tls_config.server_cert_path)
        tls_config.save_private_key(server_key, tls_config.server_key_path)
        
        # 应该需要轮换
        assert tls_config.should_rotate_keys() is True
    
    def test_rotate_keys(self, tls_config):
        """测试密钥轮换"""
        # 初始化证书
        tls_config.initialize_certificates()
        
        # 获取原始证书内容
        original_server_cert = tls_config.load_certificate(tls_config.server_cert_path)
        
        # 执行密钥轮换
        tls_config.rotate_keys()
        
        # 验证新证书不同于原始证书
        new_server_cert = tls_config.load_certificate(tls_config.server_cert_path)
        assert original_server_cert.serial_number != new_server_cert.serial_number
        
        # 验证备份目录存在
        backup_dirs = list((tls_config.cert_dir / "backup").glob("*"))
        assert len(backup_dirs) > 0


class TestKeyRotationManager:
    """密钥轮换管理器测试"""
    
    @pytest.fixture
    def temp_cert_dir(self):
        """临时证书目录"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest.fixture
    def tls_config(self, temp_cert_dir):
        """TLS配置实例"""
        return TLSConfig(cert_dir=temp_cert_dir)
    
    @pytest.fixture
    def rotation_manager(self, tls_config):
        """密钥轮换管理器实例"""
        return KeyRotationManager(tls_config)
    
    def test_generate_rotation_secret(self, rotation_manager):
        """测试生成轮换密钥"""
        secret = rotation_manager.generate_rotation_secret()
        
        assert isinstance(secret, str)
        assert len(secret) > 0
        
        # 生成的密钥应该不同
        secret2 = rotation_manager.generate_rotation_secret()
        assert secret != secret2
    
    def test_get_current_key_hash(self, rotation_manager):
        """测试获取当前密钥哈希"""
        # 初始化证书
        rotation_manager.tls_config.initialize_certificates()
        
        # 获取密钥哈希
        key_hash = rotation_manager.get_current_key_hash()
        
        assert isinstance(key_hash, str)
        assert len(key_hash) == 64  # SHA256哈希长度
        
        # 相同密钥应该产生相同哈希
        key_hash2 = rotation_manager.get_current_key_hash()
        assert key_hash == key_hash2
    
    def test_schedule_key_rotation_not_needed(self, rotation_manager):
        """测试不需要密钥轮换的情况"""
        # 初始化新证书
        rotation_manager.tls_config.initialize_certificates()
        
        # 获取原始证书
        original_cert = rotation_manager.tls_config.load_certificate(
            rotation_manager.tls_config.server_cert_path
        )
        
        # 调度密钥轮换
        rotation_manager.schedule_key_rotation()
        
        # 证书应该没有变化
        current_cert = rotation_manager.tls_config.load_certificate(
            rotation_manager.tls_config.server_cert_path
        )
        assert original_cert.serial_number == current_cert.serial_number
    
    def test_schedule_key_rotation_needed(self, rotation_manager):
        """测试需要密钥轮换的情况"""
        # 创建即将过期的证书
        ca_cert, ca_key = rotation_manager.tls_config.create_ca_certificate()
        
        from cryptography.hazmat.primitives import hashes
        from cryptography.x509.oid import NameOID
        
        server_key = rotation_manager.tls_config.generate_private_key()
        subject = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "expiring-server"),
        ])
        
        expiring_cert = x509.CertificateBuilder().subject_name(
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
            datetime.utcnow() + timedelta(days=29)  # 29天后过期
        ).sign(ca_key, hashes.SHA256())
        
        # 保存即将过期的证书
        rotation_manager.tls_config.save_certificate(ca_cert, rotation_manager.tls_config.ca_cert_path)
        rotation_manager.tls_config.save_private_key(ca_key, rotation_manager.tls_config.ca_key_path)
        rotation_manager.tls_config.save_certificate(expiring_cert, rotation_manager.tls_config.server_cert_path)
        rotation_manager.tls_config.save_private_key(server_key, rotation_manager.tls_config.server_key_path)
        
        # 调度密钥轮换
        rotation_manager.schedule_key_rotation()
        
        # 证书应该已经更新
        new_cert = rotation_manager.tls_config.load_certificate(
            rotation_manager.tls_config.server_cert_path
        )
        assert new_cert.serial_number != expiring_cert.serial_number