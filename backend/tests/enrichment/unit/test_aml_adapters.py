"""Адаптеры проверок по 115-ФЗ: формат external-mocks → DTO; незнакомый код — не «чисто»."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest

from src.modules.enrichment.application.dto.aml import AmlSubjectDTO, LicenseDTO
from src.modules.enrichment.domain.exceptions import SourceUnavailable
from src.modules.enrichment.infrastructure.adapters.aml_http import (
    PepHttpSource,
    RfmHttpSource,
    ZskHttpSource,
)
from src.modules.enrichment.infrastructure.adapters.egrul_http import EgrulHttpSource
from src.modules.enrichment.infrastructure.adapters.licenses_http import LicensesHttpSource

_SUBJECTS = (
    AmlSubjectDTO("company", "ООО «Северный ветер»", "7707115016"),
    AmlSubjectDTO("head", "Ветров Виктор Викторович"),
)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://mock")


def _answer(body: Any) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(200, json=body)


async def test_lists_request_and_hits() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "ДатаАктуальности": "2026-10-22",
                "Результаты": [
                    {
                        "id": "0",
                        "Совпадения": [
                            {"Перечень": "ЭКСТРЕМИЗМ_ТЕРРОРИЗМ", "НомерЗаписи": "ЮЛ-2026-00317"}
                        ],
                    },
                    {"id": "1", "Совпадения": []},
                ],
            },
        )

    dto = await RfmHttpSource(_client(handler), backoff=()).screen(_SUBJECTS)

    assert dto.lists_date == date(2026, 10, 22)
    assert dto.hits == ((0, "terrorism", "ЮЛ-2026-00317"),)
    [body] = seen
    assert [(s["id"], s["type"], s["inn"]) for s in body["subjects"]] == [
        ("0", "UL", "7707115016"),
        ("1", "FL", None),
    ]


async def test_unknown_list_is_a_bad_response() -> None:
    """Незнакомый перечень — проверка не выполнена, а не «совпадений нет»."""
    body = {
        "ДатаАктуальности": "2026-10-22",
        "Результаты": [
            {"id": "0", "Совпадения": [{"Перечень": "НОВЫЙ", "НомерЗаписи": "1"}]},
            {"id": "1", "Совпадения": []},
        ],
    }
    with pytest.raises(SourceUnavailable) as error:
        await RfmHttpSource(_client(_answer(body)), backoff=()).screen(_SUBJECTS)
    assert error.value.kind == "bad_response"


async def test_answer_for_fewer_subjects_is_a_bad_response() -> None:
    body = {"ДатаАктуальности": "2026-10-22", "Результаты": [{"id": "0", "Совпадения": []}]}
    with pytest.raises(SourceUnavailable):
        await RfmHttpSource(_client(_answer(body)), backoff=()).screen(_SUBJECTS)


async def test_pep_categories() -> None:
    body = {
        "Результаты": [
            {"id": "0", "ПДЛ": {"Категория": "ИПДЛ", "Должность": "Посол"}},
            {"id": "1", "ПДЛ": None},
        ]
    }
    dto = await PepHttpSource(_client(_answer(body)), backoff=()).screen(("А", "Б"))
    assert dto.hits == ((0, "foreign", "Посол"),)


async def test_zsk_levels() -> None:
    body = {"ИНН": "7707115048", "Уровень": "ВЫСОКИЙ", "ДатаАктуальности": "2026-10-22"}
    dto = await ZskHttpSource(_client(_answer(body)), backoff=()).fetch("7707115048")
    assert (dto.level, dto.as_of) == ("high", date(2026, 10, 22))


async def test_registry_corporate_founder() -> None:
    body = {
        "ИНН": "7707115062",
        "ОГРН": "1157707115060",
        "НаимПолн": "ООО «Северная дочка»",
        "Статус": {"Код": "ACTIVE"},
        "ДатаРег": "2022-10-23",
        "ОКВЭДОсн": {"Код": "46.90"},
        "Руководитель": {"ФИО": "Дочкин Дмитрий Данилович", "Должность": "ГД"},
        "Учредители": [
            {"ФИО": "Дочкин Дмитрий Данилович", "Доля": 20},
            {"Наим": "ООО «Холдинг Восток»", "ИНН": "7707115070", "Доля": 80},
        ],
        "Адрес": {"Полный": "г. Москва", "КодРегиона": "77"},
        "МассовыйАдрес": False,
        "ОрганизационнаяФорма": "ООО",
    }
    dto = await EgrulHttpSource(_client(_answer(body)), backoff=()).fetch("7707115062")
    assert [(f.name, f.share_percent, f.inn) for f in dto.founders] == [
        ("Дочкин Дмитрий Данилович", Decimal(20), None),
        ("ООО «Холдинг Восток»", Decimal(80), "7707115070"),
    ]


def _registry_with(founders: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ИНН": "7707115111",
        "ОГРН": "1157707115114",
        "НаимПолн": "ООО «Каспий-Трейд»",
        "Статус": {"Код": "ACTIVE"},
        "ДатаРег": "2022-10-23",
        "ОКВЭДОсн": {"Код": "46.90"},
        "Руководитель": {"ФИО": "Каспиев Карен Каренович", "Должность": "ГД"},
        "Учредители": founders,
        "Адрес": {"Полный": "г. Москва", "КодРегиона": "77"},
        "МассовыйАдрес": False,
        "ОрганизационнаяФорма": "ООО",
    }


async def test_registry_founder_country() -> None:
    body = _registry_with(
        [
            {"ФИО": "Каспиев Карен Каренович", "Доля": 60, "Страна": "RU"},
            {"ФИО": "Хоссейни Али Реза", "Доля": 40, "Страна": "ir"},
        ]
    )
    dto = await EgrulHttpSource(_client(_answer(body)), backoff=()).fetch("7707115111")
    assert [(f.name, f.country) for f in dto.founders] == [
        ("Каспиев Карен Каренович", None),
        ("Хоссейни Али Реза", "IR"),
    ]


async def test_registry_unknown_country_is_a_bad_response() -> None:
    body = _registry_with([{"ФИО": "Хоссейни Али Реза", "Доля": 100, "Страна": "Иран"}])
    with pytest.raises(SourceUnavailable) as exc:
        await EgrulHttpSource(_client(_answer(body)), backoff=()).fetch("7707115111")
    assert exc.value.kind == "bad_response"


async def test_licenses_only_active() -> None:
    body = {
        "ИНН": "7707083893",
        "Лицензии": [
            {
                "Номер": "Л041-01",
                "ВидДеятельности": "Медицинская деятельность",
                "ОКВЭД": "86.10",
                "Статус": "ДЕЙСТВУЕТ",
                "ДатаВыдачи": "2024-01-10",
            },
            {
                "Номер": "Л041-02",
                "ВидДеятельности": "Фармацевтическая деятельность",
                "ОКВЭД": "47.73",
                "Статус": "ПРИОСТАНОВЛЕНА",
                "ДатаВыдачи": "2023-01-10",
            },
        ],
    }
    licenses = await LicensesHttpSource(_client(_answer(body)), backoff=()).fetch("7707083893")
    assert licenses == (LicenseDTO("Л041-01", "Медицинская деятельность", "86.10"),)


async def test_licenses_unexpected_answer() -> None:
    with pytest.raises(SourceUnavailable) as exc:
        await LicensesHttpSource(_client(_answer({"ИНН": "1"})), backoff=()).fetch("1")
    assert exc.value.kind == "bad_response"
