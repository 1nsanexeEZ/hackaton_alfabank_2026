"""Consents the bank asks for before an application (on the bank's process map — right
after the client picks the terms, before pre-scoring) and what each one lets the bank
do. identity keeps them; the dashboard shows which are given."""

from dataclasses import dataclass

from src.modules.bff.domain.enums import ConsentKind, ConsentScope


@dataclass(frozen=True, slots=True)
class ConsentInfo:
    type: ConsentKind
    scope: ConsentScope
    title: str
    purpose: str
    # Without it an application cannot be submitted.
    required: bool


# In the order the cabinet shows them. credit_bureau_personal — to the head by the registry
# only: it is their own credit history.
PROFILE_CONSENTS: tuple[ConsentInfo, ...] = (
    ConsentInfo(
        "personal_data",
        "account",
        "Согласие на обработку персональных данных",
        "Банк сможет рассмотреть заявку. Без согласия заявку не подать",
        True,
    ),
    ConsentInfo(
        "credit_bureau_company",
        "organization",
        "Согласие на запрос кредитной истории компании в БКИ",
        "Банк проверит кредитную историю компании. Без согласия заявку не подать",
        True,
    ),
    ConsentInfo(
        "credit_bureau_personal",
        "account",
        "Согласие на запрос вашей кредитной истории в БКИ",
        "Банк проверит кредитную историю руководителя, и решение будет точнее",
        False,
    ),
)
