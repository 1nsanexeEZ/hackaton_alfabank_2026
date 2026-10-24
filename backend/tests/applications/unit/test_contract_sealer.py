import asyncio
from pathlib import Path

from fpdf import FPDF

from src.modules.applications.infrastructure.adapters.contract_sealer import PyHankoContractSealer


def _pdf(text: str = "contract body") -> bytes:
    pdf = FPDF()
    pdf.set_compression(False)  # the text stays findable in the bytes
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    pdf.cell(text=text)
    return bytes(pdf.output())


def test_sealed_pdf_is_intact_trusted_and_time_stamped(tmp_path: Path) -> None:
    sealer = PyHankoContractSealer(tmp_path)

    sealed = asyncio.run(sealer.seal(_pdf()))
    check = asyncio.run(sealer.check(sealed.content))

    assert check.present and check.intact and check.trusted
    assert check.timestamp_at is not None and sealed.timestamp_at == check.timestamp_at
    assert check.signer == sealer.certificate().subject
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "contract_ca.pem",
        "contract_seal.pem",
        "contract_seal_key.pem",
        "contract_tsa.pem",
        "contract_tsa_key.pem",
    ]


def test_keys_survive_a_restart(tmp_path: Path) -> None:
    first = PyHankoContractSealer(tmp_path).certificate()
    again = PyHankoContractSealer(tmp_path).certificate()

    assert again == first


def test_a_changed_byte_breaks_the_signature(tmp_path: Path) -> None:
    sealer = PyHankoContractSealer(tmp_path)
    sealed = asyncio.run(sealer.seal(_pdf())).content
    tampered = bytearray(sealed)
    tampered[sealed.index(b"contract body")] = ord("C")

    check = asyncio.run(sealer.check(bytes(tampered)))

    assert check.present and not check.intact


def test_a_key_of_another_stand_is_not_trusted(tmp_path: Path) -> None:
    sealed = asyncio.run(PyHankoContractSealer(tmp_path / "other").seal(_pdf())).content

    check = asyncio.run(PyHankoContractSealer(tmp_path / "ours").check(sealed))

    assert check.present and check.intact and not check.trusted


def test_unsigned_or_broken_files_have_no_signature(tmp_path: Path) -> None:
    sealer = PyHankoContractSealer(tmp_path)

    assert not asyncio.run(sealer.check(_pdf())).present
    assert not asyncio.run(sealer.check(b"%PDF-1.7 not really")).present
