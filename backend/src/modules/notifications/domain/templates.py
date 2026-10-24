"""Texts of the feed. Template text is trusted; every substituted value comes
from events and neighbours (company names, comments of the bank, hints) and is
HTML-escaped, so a feed item is safe to render as HTML on the frontend."""

import html
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.modules.notifications.domain.enums import FeedItemType, Priority

_SPACES = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCT = re.compile(r" +([,.:;!?)])")


class Safe(str):
    """Text that is already escaped (a rendered fragment): not escaped twice."""


def escape(value: object) -> str:
    if isinstance(value, Safe):
        return str(value)
    return html.escape(str(value), quote=True)


def _tidy(text: str) -> str:
    """A missing optional value leaves no double spaces behind."""
    text = _SPACES.sub(" ", text)
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    lines = (line.strip() for line in text.split("\n"))
    return "\n".join(line for line in lines if line)


@dataclass(frozen=True, slots=True)
class Template:
    title: str
    body: str

    def render(self, **values: object) -> tuple[str, str]:
        escaped = {key: escape(value) for key, value in values.items()}
        return _tidy(self.title.format(**escaped)), _tidy(self.body.format(**escaped))

    def fragment(self, **values: object) -> Safe:
        """The body alone, to be put into another template."""
        return Safe(self.render(**values)[1])


@dataclass(frozen=True, slots=True)
class StatusTemplate(Template):
    type: FeedItemType = "status_changed"
    priority: Priority = "normal"
    action_required: bool = False


def bullets(lines: Iterable[str]) -> Safe:
    return Safe("\n".join(f"• {escape(line)}" for line in lines))


def money(amount: Decimal) -> str:
    """3000000 -> '3 000 000 ₽', 158613.29 -> '158 613,29 ₽'."""
    if amount == amount.to_integral_value():
        text = f"{amount:,.0f}"
    else:
        text = f"{amount:,.2f}"
    return text.replace(",", " ").replace(".", ",") + " ₽"


def rate(value: Decimal) -> str:
    """Decimal('23.50') -> '23,5 %'."""
    text = format(value.normalize(), "f")
    return text.replace(".", ",") + " %"


def day(moment: datetime) -> str:
    return moment.strftime("%d.%m.%Y")


def number_label(number: str | None) -> str:
    """'№ КР-2026-000001' or nothing when the card is not available."""
    return f"№ {number}" if number else ""


# --- client: application status ------------------------------------------------

SUBMITTED = Template(
    "Заявка {number} отправлена в банк",
    "Кредит «{product}» на {amount} на {term} мес. принят в работу. "
    "О каждом этапе рассмотрения сообщим здесь.",
)

STATUS: dict[str, StatusTemplate] = {
    "in_review": StatusTemplate(
        "Заявка {number} на рассмотрении",
        "Банк проверяет данные компании и считает условия. Ничего делать не нужно.",
    ),
    "in_review_after_info": StatusTemplate(
        "Данные по заявке {number} получены",
        "Спасибо! Продолжаем рассмотрение с новыми данными.",
    ),
    "info_requested": StatusTemplate(
        "Банку нужны дополнительные данные по заявке {number}",
        "{comment}\n{documents}",
        type="info_requested",
        priority="high",
        action_required=True,
    ),
    "offer_ready": StatusTemplate(
        "Готово предложение по заявке {number}",
        "{offer}\nПримите предложение, чтобы перейти к подписанию.",
        type="offer_ready",
        priority="high",
        action_required=True,
    ),
    "signing": StatusTemplate(
        "Осталось подписать договор по заявке {number}",
        "Вы приняли предложение. Подпишите договор в кабинете — "
        "подписать может участник компании с правом подписи.",
        priority="high",
        action_required=True,
    ),
    "signed": StatusTemplate(
        "Договор по заявке {number} подписан",
        "Готовим выдачу кредита. Сообщим, когда деньги поступят на счёт.",
    ),
    "disbursed": StatusTemplate(
        "Кредит по заявке {number} выдан",
        "Деньги перечислены на расчётный счёт компании.",
    ),
    "rejected": StatusTemplate(
        "Банк не может одобрить заявку {number}",
        "{explanation}",
        priority="high",
    ),
    "offer_declined": StatusTemplate(
        "Вы отказались от предложения по заявке {number}",
        "Заявка закрыта. Можно подать новую с другими параметрами.",
        priority="low",
    ),
    "expired": StatusTemplate(
        "Предложение по заявке {number} истекло",
        "Срок действия предложения закончился. Подайте новую заявку, если кредит ещё нужен.",
    ),
    "cancelled": StatusTemplate(
        "Заявка {number} отменена",
        "Заявка закрыта по вашему запросу.",
        priority="low",
    ),
}

DEFAULT_REJECTION = "Решение принято по совокупности данных о компании."
DEFAULT_INFO_COMMENT = "Откройте заявку: там указано, что нужно уточнить."
INFO_DOCUMENTS = Template("", "Загрузите: {documents}.")

OFFER = Template(
    "",
    "{amount} на {term} мес. под {rate}, платёж {payment} в месяц. "
    "Предложение действует до {until}.",
)

STAGE = Template("{stage}", "Заявка {number}: текущий этап рассмотрения.")

# --- bank -----------------------------------------------------------------------

BANK_SUBMITTED = Template(
    "Новая заявка {number}",
    "{organization}: «{product}», {amount} на {term} мес.",
)
BANK_INFO_PROVIDED = Template(
    "Клиент ответил на запрос по заявке {number}",
    "{organization} загрузил запрошенные данные (документов: {documents}).",
)
BANK_OFFER_ACCEPTED = Template(
    "Клиент принял предложение по заявке {number}", "{organization} переходит к подписанию."
)
BANK_OFFER_DECLINED = Template(
    "Клиент отказался от предложения по заявке {number}", "{organization} закрыл заявку."
)
BANK_SIGNED = Template(
    "Договор по заявке {number} подписан", "{organization}: договор подписан, ожидает выдачи."
)
BANK_CANCELLED = Template("Заявка {number} отменена клиентом", "{organization} отменил заявку.")
BANK_TASK = Template(
    "Новая задача: {task}",
    "Заявка {number}, {organization}. {due}",
)
BANK_PROCESS_FAILED = Template(
    "Процесс по заявке {number} остановлен", "Причина: {reason}. Нужна ручная проверка."
)
BANK_AUTO_DECISION = Template(
    "Автоматическое решение по заявке {number}: {outcome}", "{explanation}"
)
BANK_MANUAL_DECISION_REJECTED = Template(
    "Решение по заявке {number} не принято", "Причина: {reason}. Проверьте задачу ещё раз."
)

# --- support tickets --------------------------------------------------------------

SUPPORT_REPLY = Template("Ответ по обращению {number}", "«{subject}»\n{preview}")
SUPPORT_STATUS: dict[str, Template] = {
    "in_progress": Template(
        "Обращение {number} взято в работу", "«{subject}»: специалист банка уже разбирается."
    ),
    "resolved": Template(
        "Обращение {number} решено",
        "«{subject}». Если вопрос остался, напишите в обращение — оно вернётся в работу.",
    ),
    "closed": Template(
        "Обращение {number} закрыто", "«{subject}». С новым вопросом создайте новое обращение."
    ),
}
BANK_SUPPORT_OPENED = Template("Новое обращение {number}", "«{subject}»\n{organization}")
BANK_SUPPORT_RETURNED = Template(
    "Обращение {number} вернулось в очередь", "«{subject}»: его снова можно взять."
)
BANK_SUPPORT_CLIENT_WROTE = Template(
    "Клиент написал в обращение {number}", "«{subject}»\n{preview}"
)

# --- client: advice and company -------------------------------------------------

HINTS = Template("Как улучшить условия", "{hints}")
PRE_APPROVED = Template("Для вас есть предодобренные предложения", "{offers}")
PRE_APPROVED_WITHDRAWN = Template(
    "Уточните данные компании",
    "Предодобренные предложения сняты: данные {organization} не подтверждены реестром. "
    "Проверьте карточку компании, и банк пересчитает предложения.",
)
ORGANIZATION_VERIFIED = Template(
    "Данные компании подтверждены", "Реквизиты {organization} совпадают с данными реестра."
)
ORGANIZATION_MISMATCH = Template(
    "Данные компании расходятся с реестром",
    "Проверьте карточку {organization}:\n{discrepancies}",
)
MEMBER_ADDED = Template(
    "Вас добавили в компанию {organization}",
    "Роль: {role}. Заявки и лента компании теперь доступны в кабинете.",
)
MEMBER_REMOVED = Template(
    "Доступ к компании {organization} закрыт", "Вас исключили из участников компании."
)
MEMBER_ROLE_CHANGED = Template(
    "Ваша роль в компании {organization} изменена", "Новая роль: {role}."
)
REPORT_SUBMITTED = Template(
    "Отчётность {period} сохранена",
    "Банк учтёт новые данные {organization} при рассмотрении заявок.",
)

DOCUMENT_TITLES: dict[str, str] = {
    "bank_statement": "выписка по расчётному счёту",
    "financial_report": "финансовая отчётность",
    "collateral_documents": "документы по залогу",
    "purchase_contract": "договор купли-продажи",
    "existing_loans_statement": "справка о текущих кредитах",
    "tax_certificate": "справка об отсутствии налоговой задолженности",
}

ROLE_TITLES: dict[str, str] = {
    "owner": "владелец",
    "director": "руководитель",
    "accountant": "бухгалтер",
    "employee": "сотрудник",
}

OUTCOME_TITLES: dict[str, str] = {
    "APPROVE": "одобрено",
    "COUNTER_OFFER": "контрпредложение",
    "REQUEST_INFO": "запрос данных",
    "MANUAL_REVIEW": "ручная проверка",
    "REJECT": "отказ",
}

TASK_TITLES: dict[str, str] = {
    "underwriting_review": "проверка заявки андеррайтером",
    "manual_review": "ручная проверка заявки",
    "document_review": "проверка документов",
}

DISCREPANCY_TITLES: dict[str, str] = {
    "head_name": "руководитель",
    "name": "наименование",
    "address": "адрес",
    "okved_main": "основной ОКВЭД",
    "registry_status": "статус в реестре",
    "kpp": "КПП",
    "inn": "ИНН",
    "ogrn": "ОГРН",
}
