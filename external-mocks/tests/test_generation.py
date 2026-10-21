from __future__ import annotations

from fastapi.testclient import TestClient

from app.data import DEMO, generate_company

# Валидный ИНН, которого нет среди демо-компаний (ИНН Сбербанка — публично известный, валидный).
_UNKNOWN_VALID = "7707083893"


def test_unknown_valid_inn_is_generated(client: TestClient) -> None:
    assert _UNKNOWN_VALID not in DEMO
    resp = client.get(f"/egrul/{_UNKNOWN_VALID}")
    assert resp.status_code == 200
    assert resp.json()["ИНН"] == _UNKNOWN_VALID


def test_generation_is_deterministic(client: TestClient) -> None:
    first = client.get(f"/egrul/{_UNKNOWN_VALID}").json()
    second = client.get(f"/egrul/{_UNKNOWN_VALID}").json()
    assert first == second


def test_generator_pure_function_deterministic() -> None:
    assert generate_company(_UNKNOWN_VALID) == generate_company(_UNKNOWN_VALID)


def test_generated_llc_has_kpp_and_form(client: TestClient) -> None:
    body = client.get(f"/egrul/{_UNKNOWN_VALID}").json()
    assert body["ОрганизационнаяФорма"] == "ООО"
    assert "КПП" in body
