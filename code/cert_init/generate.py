import os
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path("/out")
SERVICES = ("gateway", "player-manager", "collector", "game-manager", "encounter")
now = datetime.now(timezone.utc)


def write_private_key(key, destination):
    destination.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    destination.chmod(0o600)


authority_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
authority_name = x509.Name(
    [x509.NameAttribute(NameOID.COMMON_NAME, "Monster Tamer Local Development CA")]
)
authority_cert = (
    x509.CertificateBuilder()
    .subject_name(authority_name)
    .issuer_name(authority_name)
    .public_key(authority_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now - timedelta(minutes=5))
    .not_valid_after(now + timedelta(days=30))
    .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
    .add_extension(
        x509.SubjectKeyIdentifier.from_public_key(authority_key.public_key()),
        critical=False,
    )
    .add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(authority_key.public_key()),
        critical=False,
    )
    .add_extension(
        x509.KeyUsage(
            digital_signature=False,
            content_commitment=False,
            key_encipherment=False,
            data_encipherment=False,
            key_agreement=False,
            key_cert_sign=True,
            crl_sign=True,
            encipher_only=None,
            decipher_only=None,
        ),
        critical=True,
    )
    .sign(authority_key, hashes.SHA256())
)
(ROOT / "ca" / "ca.pem").write_bytes(authority_cert.public_bytes(serialization.Encoding.PEM))

for service in SERVICES:
    directory = ROOT / service
    directory.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    service_name = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, service)]
    )
    names = [x509.DNSName(service), x509.DNSName("localhost")]
    if service == "gateway":
        names.append(x509.IPAddress(ip_address("127.0.0.1")))
    certificate = (
        x509.CertificateBuilder()
        .subject_name(service_name)
        .issuer_name(authority_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName(names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(authority_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .sign(authority_key, hashes.SHA256())
    )
    (directory / "server.pem").write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    write_private_key(key, directory / "server-key.pem")
    os.chmod(directory / "server.pem", 0o644)
