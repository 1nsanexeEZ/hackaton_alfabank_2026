"""Адаптеры проверок по 115-ФЗ: формат external-mocks → DTO; незнакомый код — не «чисто»."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest

from src.modules.enrichment.application.dto.aml import AmlSubjectDTO
from src.modules.enrichment.domain.exceptions import SourceUnavailable
from src.modules.enrichment.infrastructure.adapters.aml_http import (
    PepHttpSource,
    RfmHttpSource,
    ZskHttpSource,
)
from src.modules.enrichment.infrastructure.adapters.egrul_http import EgrulHttpSource

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
