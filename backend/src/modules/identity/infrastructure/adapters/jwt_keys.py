import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@dataclass(frozen=True)
class SigningKeys:
    private_key: rsa.RSAPrivateKey
    public_key: rsa.RSAPublicKey
    kid: str


def _key_id(public_key: rsa.RSAPublicKey) -> str:
    der = public_key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return base64.urlsafe_b64encode(hashlib.sha256(der).digest()).decode().rstrip("=")[:16]


def _generate(private_path: Path, public_path: Path) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    private_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )


def load_signing_keys(private_path: Path, public_path: Path, generate: bool) -> SigningKeys:
    if not private_path.exists():
        if not generate:
            raise RuntimeError(f"JWT private key not found: {private_path}")
        _generate(private_path, public_path)

    private_key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise RuntimeError(f"{private_path} is not an RSA private key")
    # The public key is always derived from the private one, the .pem file is
    # written only for services that verify tokens without the private key.
    public_key = private_key.public_key()
    return SigningKeys(private_key=private_key, public_key=public_key, kid=_key_id(public_key))
