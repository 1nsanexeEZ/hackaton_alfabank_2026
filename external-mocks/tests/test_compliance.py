from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEMO_INNS


def _screen(client: TestClient, *subjects: dict) -> list[list[dict]]:
    resp = client.post("/rfm/screen", json={"request_id": "r1", "subjects": list(subjects)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ДатаАктуальности"]
    return [result["Совпадения"] for result in body["Результаты"]]


def _pep(client: TestClient, fio: str) -> dict | None:
    resp = client.post("/pep/screen", json={"persons": [{"id": "p1", "fio": fio}]})
    assert resp.status_code == 200
    return resp.json()["Результаты"][0]["ПДЛ"]


@pytest.mark.parametrize("inn", DEMO_INNS)
def test_demo_companies_are_clean(client: TestClient, inn: str) -> None:
    """Сценарии S-1…S-9 не меняются: у демо-компаний бэкенда ни совпадений, ни риска ЗСК."""
    egrul = client.get(f"/egrul/{inn}").json()
    people = [egrul["Руководитель"]["ФИО"], *(f["ФИО"] for f in egrul["Учредители"])]
    subjects = [{"id": "c", "type": "UL", "name": egrul["НаимПолн"], "inn": inn}]
    subjects += [{"id": str(i), "type": "FL", "name": fio} for i, fio in enumerate(people)]
    assert all(hits == [] for hits in _screen(client, *subjects))
    assert all(_pep(client, fio) is None for fio in people)
    assert client.get(f"/zsk/{inn}").json()["Уровень"] == "НИЗКИЙ"


def test_listed_company_by_inn(client: TestClient) -> None:
    [hits] = _screen(
        client, {"id": "c", "type": "UL", "name": "Северный ветер", "inn": "7707115016"}
    )
    assert hits == [{"Перечень": "ЭКСТРЕМИЗМ_ТЕРРОРИЗМ", "НомерЗаписи": "ЮЛ-2026-00317"}]


def test_frozen_person_matches_regardless_of_case_and_yo(client: TestClient) -> None:
    [hits] = _screen(client, {"id": "h", "type": "FL", "name": "  МОРОЗОВ максим  Маркович "})
    assert hits[0]["Перечень"] == "МВК"


def test_foreign_pep(client: TestClient) -> None:
    assert _pep(client, "Послов Петр Павлович") == {
        "Категория": "ИПДЛ",
        "Должность": "Посол иностранного государства",
    }


def test_zsk_levels(client: TestClient) -> None:
    assert client.get("/zsk/7707115048").json()["Уровень"] == "ВЫСОКИЙ"
    assert client.get("/zsk/7707115055").json()["Уровень"] == "СРЕДНИЙ"


def test_zsk_invalid_inn_404(client: TestClient) -> None:
    assert client.get("/zsk/1234567890").status_code == 404


def test_corporate_founder_in_registry(client: TestClient) -> None:
    founders = client.get("/egrul/7707115062").json()["Учредители"]
    assert {"ФИО": "Дочкин Дмитрий Данилович", "Доля": 20} in founders
    assert {"Наим": "ООО «Холдинг Восток»", "ИНН": "7707115070", "Доля": 80} in founders
    holding = client.get("/egrul/7707115070").json()["Учредители"]
    assert holding == [{"ФИО": "Цепочкин Цезарь Цезаревич", "Доля": 100}]
    [hits] = _screen(client, {"id": "b", "type": "FL", "name": "Цепочкин Цезарь Цезаревич"})
    assert hits[0]["Перечень"] == "ФРОМУ"


def test_generated_answers_are_deterministic(client: TestClient) -> None:
    subject = {"id": "h", "type": "FL", "name": "Руководитель № 0001"}
    assert _screen(client, subject) == _screen(client, subject)
    assert client.get("/zsk/7707083893").json() == client.get("/zsk/7707083893").json()


def test_third_parties_from_the_application(client: TestClient) -> None:
    """Выгодоприобретатель или залогодатель, которого клиент укажет в заявке: человек — по ФИО,
    организация — по ИНН."""
    person, company = _screen(
        client,
        {"id": "b", "type": "FL", "name": "Посредников Павел Павлович"},
        {"id": "p", "type": "UL", "name": "ООО «Транзитный агент»", "inn": "7707115094"},
    )
    assert person[0]["Перечень"] == "ЭКСТРЕМИЗМ_ТЕРРОРИЗМ"
    assert company[0]["Перечень"] == "МВК"


def test_minority_founder_in_the_lists(client: TestClient) -> None:
    """Учредитель с 20% — не бенефициар, но в перечне: банк проверяет всех учредителей."""
    founders = client.get("/egrul/7707115104").json()["Учредители"]
    assert {"ФИО": "Малодолев Мирон Миронович", "Доля": 20} in founders
    [hits] = _screen(client, {"id": "f", "type": "FL", "name": "Малодолев Мирон Миронович"})
    assert hits[0]["Перечень"] == "ЭКСТРЕМИЗМ_ТЕРРОРИЗМ"


def test_foreign_founders_carry_the_country(client: TestClient) -> None:
    founders = client.get("/egrul/7707115111").json()["Учредители"]
    assert {"ФИО": "Хоссейни Али Реза", "Доля": 40, "Страна": "IR"} in founders
    assert {"ФИО": "Каспиев Карен Каренович", "Доля": 60} in founders
    assert {"ФИО": "Шмидт Ганс", "Доля": 30, "Страна": "DE"} in (
        client.get("/egrul/7707115129").json()["Учредители"]
    )


@pytest.mark.parametrize("inn", DEMO_INNS)
def test_demo_companies_have_no_foreign_founders(client: TestClient, inn: str) -> None:
    assert all("Страна" not in f for f in client.get(f"/egrul/{inn}").json()["Учредители"])
