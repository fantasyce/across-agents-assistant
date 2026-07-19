from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from ipaddress import ip_address
from pathlib import Path
from typing import Any
import os
import tempfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


DEVICE_CERTIFICATE_TTL_HOURS = 30 * 24
SERVICE_CERTIFICATE_TTL_DAYS = 90
CERTIFICATE_ROTATION_WINDOW_DAYS = 7


class WorkerCertificateAuthority:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.ca_key_path = self.root / "ca-key.pem"
        self.ca_certificate_path = self.root / "ca-certificate.pem"
        self.server_key_path = self.root / "server-key.pem"
        self.server_certificate_path = self.root / "server-certificate.pem"
        self.relay_client_key_path = self.root / "relay-client-key.pem"
        self.relay_client_certificate_path = self.root / "relay-client-certificate.pem"

    def ensure(self, bind_host: str) -> dict[str, Any]:
        ca_key, ca_certificate = self._load_or_create_ca()
        server_key, server_certificate = self._create_server(ca_key, ca_certificate, bind_host)
        return {
            "ca_certificate": str(self.ca_certificate_path),
            "server_certificate": str(self.server_certificate_path),
            "server_private_key": str(self.server_key_path),
            "certificate_fingerprint": server_certificate.fingerprint(hashes.SHA256()).hex(),
            "not_after": server_certificate.not_valid_after_utc.timestamp(),
        }

    def issue_device(
        self,
        *,
        node_id: str,
        public_key_pem: str,
        ttl_hours: int = DEVICE_CERTIFICATE_TTL_HOURS,
    ) -> dict[str, Any]:
        ca_key, ca_certificate = self._load_or_create_ca()
        public_key = serialization.load_pem_public_key(public_key_pem.encode("ascii"))
        now = datetime.now(UTC)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, node_id)]))
            .issuer_name(ca_certificate.subject)
            .public_key(public_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=2))
            .not_valid_after(now + timedelta(hours=max(1, min(int(ttl_hours), 90 * 24))))
            .add_extension(x509.SubjectAlternativeName([x509.UniformResourceIdentifier(f"spiffe://across.local/worker/{node_id}")]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=True)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=False, key_cert_sign=False, key_agreement=False, content_commitment=False, data_encipherment=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .sign(ca_key, hashes.SHA256())
        )
        pem = certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")
        return {
            "certificate_pem": pem,
            "ca_certificate_pem": ca_certificate.public_bytes(serialization.Encoding.PEM).decode("ascii"),
            "serial_number": format(certificate.serial_number, "x"),
            "fingerprint": certificate.fingerprint(hashes.SHA256()).hex(),
            "not_after": certificate.not_valid_after_utc.timestamp(),
        }

    def ensure_relay_client(self, *, node_id: str) -> dict[str, Any]:
        ca_key, ca_certificate = self._load_or_create_ca()
        if self.relay_client_key_path.exists() and self.relay_client_certificate_path.exists():
            key = serialization.load_pem_private_key(self.relay_client_key_path.read_bytes(), password=None)
            certificate = x509.load_pem_x509_certificate(self.relay_client_certificate_path.read_bytes())
            names = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
            if names and names[0].value == node_id and certificate.not_valid_after_utc > datetime.now(UTC) + timedelta(days=CERTIFICATE_ROTATION_WINDOW_DAYS):
                return {
                    "certificate": str(self.relay_client_certificate_path),
                    "private_key": str(self.relay_client_key_path),
                    "ca_certificate": str(self.ca_certificate_path),
                    "fingerprint": certificate.fingerprint(hashes.SHA256()).hex(),
                }
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(UTC)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, node_id)]))
            .issuer_name(ca_certificate.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=2))
            .not_valid_after(now + timedelta(days=SERVICE_CERTIFICATE_TTL_DAYS))
            .add_extension(x509.SubjectAlternativeName([x509.UniformResourceIdentifier(f"spiffe://across.local/node/{node_id}")]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=True)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=True, key_cert_sign=False, key_agreement=False, content_commitment=False, data_encipherment=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .sign(ca_key, hashes.SHA256())
        )
        _atomic_bytes(self.relay_client_key_path, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()), 0o600)
        _atomic_bytes(self.relay_client_certificate_path, certificate.public_bytes(serialization.Encoding.PEM), 0o644)
        return {
            "certificate": str(self.relay_client_certificate_path),
            "private_key": str(self.relay_client_key_path),
            "ca_certificate": str(self.ca_certificate_path),
            "fingerprint": certificate.fingerprint(hashes.SHA256()).hex(),
        }

    def _load_or_create_ca(self):
        if self.ca_key_path.exists() and self.ca_certificate_path.exists():
            key = serialization.load_pem_private_key(self.ca_key_path.read_bytes(), password=None)
            certificate = x509.load_pem_x509_certificate(self.ca_certificate_path.read_bytes())
            return key, certificate
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        now = datetime.now(UTC)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Across Worker Local CA")])
        certificate = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=2))
            .not_valid_after(now + timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=False, key_cert_sign=True, key_agreement=False, content_commitment=False, data_encipherment=False, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
            .sign(key, hashes.SHA256())
        )
        _atomic_bytes(self.ca_key_path, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()), 0o600)
        _atomic_bytes(self.ca_certificate_path, certificate.public_bytes(serialization.Encoding.PEM), 0o644)
        return key, certificate

    def _create_server(self, ca_key, ca_certificate, bind_host: str):
        if self.server_key_path.exists() and self.server_certificate_path.exists():
            existing_key = serialization.load_pem_private_key(self.server_key_path.read_bytes(), password=None)
            existing_certificate = x509.load_pem_x509_certificate(self.server_certificate_path.read_bytes())
            try:
                sans = existing_certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
                names = {str(value) for value in sans.get_values_for_type(x509.DNSName)}
                names.update(str(value) for value in sans.get_values_for_type(x509.IPAddress))
            except x509.ExtensionNotFound:
                names = set()
            if bind_host in names and existing_certificate.not_valid_after_utc > datetime.now(UTC) + timedelta(days=CERTIFICATE_ROTATION_WINDOW_DAYS):
                return existing_key, existing_certificate
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(UTC)
        try:
            san = x509.IPAddress(ip_address(bind_host))
        except ValueError:
            san = x509.DNSName(bind_host)
        certificate = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, bind_host)]))
            .issuer_name(ca_certificate.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=2))
            .not_valid_after(now + timedelta(days=SERVICE_CERTIFICATE_TTL_DAYS))
            .add_extension(x509.SubjectAlternativeName([san]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=True)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=True, key_cert_sign=False, key_agreement=False, content_commitment=False, data_encipherment=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .sign(ca_key, hashes.SHA256())
        )
        _atomic_bytes(self.server_key_path, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()), 0o600)
        _atomic_bytes(self.server_certificate_path, certificate.public_bytes(serialization.Encoding.PEM), 0o644)
        return key, certificate


def _atomic_bytes(path: Path, value: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.chmod(mode)
    os.replace(temporary, path)
