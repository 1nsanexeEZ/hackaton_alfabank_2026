"""The bank's signature on the contract PDF: PAdES with a time-stamp, by pyHanko.

The demo stand has its own small CA: a root, the bank's signing certificate
(ECDSA P-256) and a time-stamping authority (RSA, the only key type pyHanko's
in-process TSA signs with). Keys are made on the first signature and kept next
to the JWT keys (the `jwt-keys` volume in docker). In production the signature
is made by a certified tool with GOST R 34.10-2012 keys and the TSA of an
accredited CA; the port stays the same.
"""

import io
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from asn1crypto import keys as asn1_keys
from asn1crypto import x509 as asn1_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.types import CertificateIssuerPrivateKeyTypes
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields, signers
from pyhanko.sign.timestamps.dummy_client import DummyTimeStamper
from pyhanko.sign.validation import async_validate_pdf_signature
from pyhanko_certvalidator import ValidationContext
from pyhanko_certvalidator.registry import SimpleCertificateStore

from src.modules.applications.application.dto.contract_documents import (
    BankCertificateDTO,
    SealCheckDTO,
    SealedPdfDTO,
)
from src.modules.applications.application.interfaces.contracts import ContractSealer

logger = logging.getLogger(__name__)

ORGANIZATION = "АО «Альфа-Банк»"
SIGNER = "АО «Альфа-Банк» (демо)"
CA_NAME = "Демо-УЦ Кредитного кабинета"
TSA_NAME = "Метки времени демо-стенда"
STAND = "Демо-стенд Альфа Хак 2026"
_FILES = ("ca.pem", "seal_key.pem", "seal.pem", "tsa_key.pem", "tsa.pem")


@dataclass(frozen=True, slots=True)
class _Keyring:
    ca: x509.Certificate
    seal_key: ec.EllipticCurvePrivateKey
    seal: x509.Certificate
    tsa_key: rsa.RSAPrivateKey
    tsa: x509.Certificate


class PyHankoContractSealer(ContractSealer):
    def __init__(self, keys_dir: Path) -> None:
        self._dir = keys_dir
        self._keyring: _Keyring | None = None

    def _keys(self) -> _Keyring:
        if self._keyring is None:
            self._keyring = _load_or_create(self._dir)
        return self._keyring

    def certificate(self) -> BankCertificateDTO:
        seal = self._keys().seal
        return BankCertificateDTO(
            subject=SIGNER,
            serial=f"{seal.serial_number:X}",
            issuer=CA_NAME,
            valid_from=seal.not_valid_before_utc,
            valid_to=seal.not_valid_after_utc,
        )

    async def seal(self, pdf: bytes) -> SealedPdfDTO:
        keys = self._keys()
        store = SimpleCertificateStore.from_certs([_asn1_cert(keys.ca)])
        signer = signers.SimpleSigner(
            signing_cert=_asn1_cert(keys.seal),
            signing_key=_asn1_key(keys.seal_key),
            cert_registry=store,
        )
        stamper = DummyTimeStamper(
            tsa_cert=_asn1_cert(keys.tsa),
            tsa_key=_asn1_key(keys.tsa_key),
            certs_to_embed=store,
        )
        meta = signers.PdfSignatureMetadata(
            field_name="BankSignature",
            subfilter=fields.SigSeedSubFilter.PADES,
            reason="Подписание кредитного договора",
            location="Москва",
        )
        signed_at = datetime.now(UTC)
        output = await signers.async_sign_pdf(
            IncrementalPdfFileWriter(io.BytesIO(pdf)), meta, signer=signer, timestamper=stamper
        )
        content = output.getvalue()
        check = await self.check(content)
        return SealedPdfDTO(content, check.signed_at or signed_at, check.timestamp_at)

    async def check(self, pdf: bytes) -> SealCheckDTO:
        try:
            signatures = PdfFileReader(io.BytesIO(pdf)).embedded_signatures
        except Exception:  # noqa: BLE001 — not a PDF or a broken one
            return SealCheckDTO(False, False, False, None, None, None)
        if not signatures:
            return SealCheckDTO(False, False, False, None, None, None)
        context = self._validation_context()
        try:
            status = await async_validate_pdf_signature(
                signatures[-1], signer_validation_context=context, ts_validation_context=context
            )
        except Exception:  # noqa: BLE001 — a damaged signature is an invalid one
            logger.info("Contract signature could not be validated", exc_info=True)
            return SealCheckDTO(True, False, False, None, None, None)
        timestamp = status.timestamp_validity.timestamp if status.timestamp_validity else None
        subject = status.signing_cert.subject.native.get("common_name")
        return SealCheckDTO(
            present=True,
            intact=bool(status.intact and status.valid),
            trusted=bool(status.trusted),
            signer=subject,
            signed_at=timestamp or status.signer_reported_dt,
            timestamp_at=timestamp,
        )

    def _validation_context(self) -> ValidationContext:
        ca = _asn1_cert(self._keys().ca)
        return ValidationContext(trust_roots=[ca], allow_fetching=False)


def _load_or_create(directory: Path) -> _Keyring:
    paths = [directory / f"contract_{name}" for name in _FILES]
    if all(path.exists() for path in paths):
        ca, seal_key, seal, tsa_key, tsa = (path.read_bytes() for path in paths)
        seal_private = serialization.load_pem_private_key(seal_key, password=None)
        tsa_private = serialization.load_pem_private_key(tsa_key, password=None)
        assert isinstance(seal_private, ec.EllipticCurvePrivateKey)
        assert isinstance(tsa_private, rsa.RSAPrivateKey)
        return _Keyring(
            ca=x509.load_pem_x509_certificate(ca),
            seal_key=seal_private,
            seal=x509.load_pem_x509_certificate(seal),
            tsa_key=tsa_private,
            tsa=x509.load_pem_x509_certificate(tsa),
        )
    keyring = _create()
    directory.mkdir(parents=True, exist_ok=True)
    blobs = (
        keyring.ca.public_bytes(serialization.Encoding.PEM),
        _pem_key(keyring.seal_key),
        keyring.seal.public_bytes(serialization.Encoding.PEM),
        _pem_key(keyring.tsa_key),
        keyring.tsa.public_bytes(serialization.Encoding.PEM),
    )
    for path, blob in zip(paths, blobs, strict=True):
        path.write_bytes(blob)
    logger.info("Created the demo signing keys of contracts in %s", directory)
    return keyring


def _create() -> _Keyring:
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = _name(CA_NAME, STAND)
    ca = _certificate(ca_name, ca_name, ca_key, ca_key, authority=True, days=3650)
    seal_key = ec.generate_private_key(ec.SECP256R1())
    seal = _certificate(_name(SIGNER, ORGANIZATION), ca_name, seal_key, ca_key, days=365)
    tsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    tsa = _certificate(
        _name(TSA_NAME, STAND),
        ca_name,
        tsa_key,
        ca_key,
        days=3650,
        usage=[ExtendedKeyUsageOID.TIME_STAMPING],
    )
    return _Keyring(ca, seal_key, seal, tsa_key, tsa)


def _name(common_name: str, organization: str) -> x509.Name:
    return x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "RU"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ]
    )


def _certificate(
    subject: x509.Name,
    issuer: x509.Name,
    key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey,
    issuer_key: CertificateIssuerPrivateKeyTypes,
    *,
    authority: bool = False,
    days: int,
    usage: list[x509.ObjectIdentifier] | None = None,
) -> x509.Certificate:
    start = datetime.now(UTC) - timedelta(minutes=5)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(start)
        .not_valid_after(start + timedelta(days=days))
        .add_extension(x509.BasicConstraints(ca=authority, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=not authority,
                content_commitment=not authority,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=authority,
                crl_sign=authority,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
    )
    if usage:
        builder = builder.add_extension(x509.ExtendedKeyUsage(usage), critical=True)
    return builder.sign(issuer_key, hashes.SHA256())


def _pem_key(key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def _asn1_cert(certificate: x509.Certificate) -> asn1_x509.Certificate:
    return asn1_x509.Certificate.load(certificate.public_bytes(serialization.Encoding.DER))


def _asn1_key(key: ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey) -> asn1_keys.PrivateKeyInfo:
    return asn1_keys.PrivateKeyInfo.load(
        key.private_bytes(
            serialization.Encoding.DER,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
