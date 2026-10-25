"""Scenarios S-1…S-10 as folders of numbered steps, the same requests as
tests/scenarios/test_s1_s8.py makes.

A step takes ids from the answers of the steps before it (application,
document, task, offer hash), so a folder is sent top to bottom without typing
anything. Every scenario ends in a final status of the application: a company
keeps one active application per product, and a scenario run again would get
409 `duplicate_active` otherwise.
"""

from typing import Any

from scripts.yaak.accounts import ACCOUNTS, INN, token
from scripts.yaak.collection import NO_AUTH, Collection, Raw, answer, bearer, model_id, var
from scripts.yaak.reference import PDF_STUB, startup_plan, statement_csv, url_of

_ASYNC = (
    "Решение процесс принимает асинхронно (Kafka, BPMN), обычно за 2–5 секунд. "
    "Если статус ещё `submitted` или `in_review` без нужного этапа — отправьте шаг ещё раз."
)


class Scenario:
    """A folder of numbered steps; `who` is the client whose token the steps use."""

    def __init__(
        self, collection: Collection, parent: str, code: str, title: str, who: str, about: str
    ) -> None:
        self.collection = collection
        self.code = code
        self.who = who
        login, person = ACCOUNTS[who]
        self.folder = collection.folder(
            f"scenario/{code}",
            f"{code}. {title}",
            parent=parent,
            description=f"{about}\n\nВходит {person} (`{login}`). Шаги отправляются по порядку.",
        )
        self.variables: dict[str, str] = {}
        self._count = 0

    def id(self, key: str) -> str:
        return model_id("rq", f"scenario/{self.code}/{key}")

    def answer(self, key: str, path: str, *, behavior: str = "smart") -> str:
        return answer(self.id(key), path, behavior=behavior)

    def step(
        self,
        key: str,
        name: str,
        method: str,
        path: str,
        *,
        who: str | None = None,
        note: str = "",
        body: Any = None,
        params: dict[str, str] | None = None,
        query: dict[str, str] | None = None,
        url: str | None = None,
        content_type: str = "application/json",
    ) -> None:
        self._count += 1
        params = params or {}
        if url is None:
            url, names = url_of(path)
        else:
            names = []
        who = self.who if who is None else who
        self.collection.request(
            self.id(key),
            f"{self._count:02d}. {name}",
            method,
            url,
            folder=self.folder,
            auth=bearer(token(who)) if who else NO_AUTH,
            description=note,
            params=[(f":{n}", params.get(n, var(n)), True) for n in names]
            + [(n, v, True) for n, v in (query or {}).items()],
            body=body,
            content_type=content_type,
        )

    def finish(self) -> None:
        self.collection.environment(
            f"scenario/{self.code}",
            f"Переменные {self.code}",
            self.variables,
            parent_model="folder",
            parent_id=self.folder,
        )

    # --- steps a client and an underwriter make ---------------------------

    def company(self, company: str) -> None:
        inn = INN[company]
        self.step(
            "company",
            "Мои компании",
            "GET",
            "/organizations",
            note=f"Компания с ИНН {inn}: её id — переменная папки `organization_id`.",
        )
        self.variables["organization_id"] = self.answer("company", f'$[?(@.inn=="{inn}")].id')

    def draft(
        self,
        product: str,
        amount: str,
        term: int,
        *,
        purpose: str = "working_capital",
        collateral: dict[str, Any] | None = None,
        product_fields: dict[str, Any] | None = None,
    ) -> None:
        self.step(
            "create",
            "Создать черновик",
            "POST",
            "/applications",
            note=(
                "201, статус `draft`; реквизиты компании банк подставляет сам. id — переменная "
                "`application_id`.\n\n409 `duplicate_active` — у компании осталась активная заявка "
                "на этот продукт с прошлого прогона: её id в `details.application_id`, доведите её "
                "до конца или отмените («Справочник API → Заявки → Отменить заявку»)."
            ),
            body={"organization_id": var("organization_id"), "product_code": product},
        )
        self.variables["application_id"] = self.answer("create", "$.id")
        body: dict[str, Any] = {
            "version": Raw(self.answer("create", "$.version")),
            "request": {"amount": amount, "term_months": term, "purpose": purpose},
            "consents": {"personal_data": True, "credit_bureau": True},
            # 115-ФЗ: клиент действует к своей выгоде (вопрос формы заявки).
            "beneficiary": {"acts_for_third_party": False},
        }
        if collateral is not None:
            body["collateral"] = collateral
        if product_fields is not None:
            body["product_fields"] = product_fields
        self.step(
            "fill",
            "Заполнить черновик",
            "PATCH",
            "/applications/{application_id}",
            note=(
                "200: сумма, срок, цель, согласия на обработку данных и запрос в БКИ и ответ, что "
                "клиент действует к своей выгоде (115-ФЗ; без ответа заявку решает человек)."
            ),
            body=body,
        )

    def document(self, document_type: str, *, statement: str | None = None) -> None:
        if statement is None:
            content, content_type, filename = PDF_STUB, "application/pdf", f"{document_type}.pdf"
        else:
            content = statement_csv(statement)
            content_type, filename = "text/csv", f"{statement}.csv"
        announce = f"{document_type}/announce"
        self.step(
            announce,
            f"Документ {document_type}: заявить файл",
            "POST",
            "/applications/{application_id}/documents",
            note="201: документ `pending_upload` и presigned URL для загрузки (`upload`).",
            body={
                "type": document_type,
                "filename": filename,
                "content_type": content_type,
                "size_bytes": len(content.encode()),
            },
        )
        self.step(
            f"{document_type}/upload",
            f"Документ {document_type}: загрузить в хранилище",
            "PUT",
            "",
            who="",
            url=self.answer(announce, "$.upload.url"),
            note=(
                "200 от MinIO: файл идёт прямо в хранилище по ссылке из прошлого шага, без токена."
                + (
                    f" Синтетическая выписка `backend/seed/statements/{filename}`."
                    if statement
                    else ""
                )
            ),
            body=content,
            content_type=content_type,
        )
        self.step(
            f"{document_type}/confirm",
            f"Документ {document_type}: подтвердить загрузку",
            "POST",
            "/applications/{application_id}/documents/{document_id}/confirm",
            params={"document_id": self.answer(announce, "$.document.id")},
            note="200, документ `uploaded`: backend проверил, что файл лежит в хранилище.",
        )

    def submit(self) -> None:
        self.step(
            "submit",
            "Подать заявку",
            "POST",
            "/applications/{application_id}/submit",
            note=(
                "200, статус `submitted`. Дальше заявку ведёт процесс: проверка данных, обогащение "
                "из внешних источников, скоринг, решение."
            ),
        )

    def card(self, key: str, name: str, expected: str, *, who: str | None = None) -> None:
        self.step(
            key,
            name,
            "GET",
            "/applications/{application_id}",
            who=who,
            note=f"Ожидаем: {expected}\n\n{_ASYNC}",
        )

    def underwriter(self, key: str, result: dict[str, Any], *, why: str) -> None:
        card = f"{key}/card"
        self.step(
            card,
            "Андеррайтер: карточка заявки",
            "GET",
            "/bff/backoffice/applications/{application_id}",
            who="underwriter",
            note=(
                "Что видит андеррайтер: данные заявки и компании, обогащение, скоринг обеих "
                "моделей, проверки 115-ФЗ, процесс. В `task` — его задача по заявке.\n\n"
                "`task: null` — процесс ещё не дошёл до андеррайтера: отправьте шаг ещё раз."
            ),
        )
        task = self.answer(card, "$.task.id")
        self.step(
            f"{key}/claim",
            "Андеррайтер: взять задачу",
            "POST",
            "/tasks/{task_id}/claim",
            who="underwriter",
            params={"task_id": task},
            note="200: задача назначена на андеррайтера, закрыть её может только он.",
        )
        self.step(
            f"{key}/complete",
            "Андеррайтер: решение",
            "POST",
            "/tasks/{task_id}/complete",
            who="underwriter",
            params={"task_id": task},
            note=f"200, задача закрыта, процесс идёт дальше в той же транзакции. {why}",
            body=result,
        )

    def accept_and_sign(self, *, who: str | None = None) -> None:
        self.step(
            "accept",
            "Принять предложение",
            "POST",
            "/applications/{application_id}/offer/accept",
            who=who,
            note="200, статус `signing`: дальше договор и подпись.",
        )
        self.contract_and_sign(who=who)

    def contract_and_sign(self, *, who: str | None = None, suffix: str = "") -> None:
        contract = f"contract{suffix}"
        self.step(
            contract,
            "Договор",
            "GET",
            "/applications/{application_id}/contract",
            who=who,
            note=(
                "200, договор `unsigned`: заёмщик, условия, график платежей, УИд сделки "
                "(`uid`) и PDF-проект в `document` (`kind: draft`). `offer_hash` — отпечаток "
                "условий, `document.sha256` — хеш проекта: подпись идёт именно под ними."
            ),
        )
        self.step(
            f"draft{suffix}",
            "Договор: PDF-проект",
            "GET",
            "/applications/{application_id}/contract/document",
            who=who,
            query={"kind": "draft"},
            note="200 `application/pdf`: проект договора с плашкой «Проект», УИд и QR-кодом.",
        )
        rules = f"rules{suffix}"
        self.step(
            rules,
            "Правила электронного взаимодействия",
            "GET",
            "/esign/rules",
            who="",
            note=(
                "200: соглашение о простой электронной подписи (63-ФЗ, ст. 6 и 9). Его "
                "`version` клиент принимает при подписании."
            ),
        )
        self.step(
            f"sign{suffix}",
            "Подписать договор",
            "POST",
            "/applications/{application_id}/sign",
            who=who,
            note=(
                "200: простая электронная подпись — пароль ещё раз (step-up), хеш проекта "
                "и версия правил. Сразу после неё банк подписывает итоговый PDF своей "
                "подписью (PAdES с меткой времени). Деньги выдаёт АБС, это мок."
            ),
            body={
                "password": var("demo_password"),
                "offer_hash": self.answer(contract, "$.offer_hash"),
                "document_hash": self.answer(contract, "$.document.sha256"),
                "rules_version": self.answer(rules, "$.version"),
            },
        )
        sealed = f"sealed{suffix}"
        self.step(
            sealed,
            "Договор после подписи",
            "GET",
            "/applications/{application_id}/contract",
            who=who,
            note=(
                "200, договор `signed`; в `document` — итоговый PDF (`kind: signed`) "
                "и `verify_url` — куда ведёт QR-код договора."
            ),
        )
        self.step(
            f"signed_pdf{suffix}",
            "Договор: подписанный PDF",
            "GET",
            "/applications/{application_id}/contract/document",
            who=who,
            query={"kind": "signed"},
            note=(
                "200 `application/pdf`: договор со штампами обеих подписей и листом подписания. "
                "Подпись банка видна в панели подписей программы просмотра PDF."
            ),
        )
        self.step(
            f"verify{suffix}",
            "Проверка договора по QR",
            "GET",
            "/contracts/verify/{document_id}",
            who="",
            params={"document_id": self.answer(sealed, "$.document.id")},
            note=(
                "200 без входа: кто и когда подписал (клиент — с инициалами), сертификат "
                "и метка времени банка, `log_intact` — журнал подписания не разорван."
            ),
        )

    def disbursed(self) -> None:
        self.card(
            "disbursed",
            "Карточка: выдача",
            "статус `disbursed`, в `disbursement` — `simulated: true`.",
        )


def _uw(decision: str, comment: str, **terms: Any) -> dict[str, Any]:
    return {"decision": decision, **terms, "comment": comment}


def add_scenarios(collection: Collection) -> None:
    root = collection.folder(
        "scenarios",
        "Сценарии S-1…S-10",
        parent=None,
        description=(
            "Сценарии проверки из README: каждый — папка шагов, которые отправляются по порядку. "
            "Id заявки, документа, задачи и хеш оферты берутся из ответов прошлых шагов.\n\n"
            "Решение банк принимает асинхронно: если шаг «Карточка» показывает ещё не тот статус — "
            "подождите пару секунд и отправьте его ещё раз. Сценарий доводит заявку до "
            "финального статуса, поэтому его можно пройти снова."
        ),
    )
    for build in (_s1, _s2, _s3, _s4, _s5, _s6, _s7, _s8, _s9, _s10):
        build(collection, root)


def _s1(collection: Collection, root: str) -> None:
    s = Scenario(
        collection,
        root,
        "S-1",
        "Ромашка: автоматическое одобрение",
        "romashka",
        "«Кредит без залога», 3 млн ₽ на 24 месяца: благополучный заёмщик, банк одобряет "
        "автоматически → клиент принимает предложение, подписывает договор → выдача.",
    )
    s.company("romashka")
    s.draft("UNSECURED", "3000000", 24)
    s.submit()
    s.card(
        "decision",
        "Карточка: решение",
        "статус `offer_ready`, `offer.kind` = `as_requested` на 3 000 000, "
        "`decision_summary.outcome` = `APPROVE`, этап «Решение готово».",
    )
    s.accept_and_sign()
    s.disbursed()
    s.step(
        "process",
        "Процесс по заявке",
        "GET",
        "/processes/{application_id}",
        who="underwriter",
        note="`completed`; в `visited_node_ids` нет `underwriter_review`: человек не участвовал.",
    )
    s.finish()


def _s2(collection: Collection, root: str) -> None:
    s = Scenario(
        collection,
        root,
        "S-2",
        "ИП Иванов: андеррайтер снижает сумму",
        "ivanov",
        "«Кредит без залога», 5 млн ₽ на 24 месяца, с налоговой декларацией и выпиской: обе модели "
        "в жёлтой зоне (грейд E) → андеррайтер видит оценки и прогноз кассового разрыва и делает "
        "контрпредложение на 3 млн → клиент принимает и подписывает.",
    )
    s.company("ivanov")
    s.draft("UNSECURED", "5000000", 24)
    s.document("tax_return")
    s.document("bank_statement", statement="ivanov")
    s.submit()
    s.card("review", "Карточка: у специалиста", "статус `in_review`, этап «Заявка у специалиста».")
    s.underwriter(
        "uw",
        _uw(
            "counter_offer",
            "Обе модели в жёлтой зоне, кассовый разрыв в ноябре: снижаем сумму",
            amount="3000000",
            term_months=24,
            rate="25",
        ),
        why="Контрпредложение: 3 млн под 25%.",
    )
    s.card(
        "offer",
        "Карточка: контрпредложение",
        "статус `offer_ready`, `offer.kind` = `counter`, 3 000 000.",
    )
    s.accept_and_sign()
    s.disbursed()
    s.finish()


def _s3(collection: Collection, root: str) -> None:
    s = Scenario(
        collection,
        root,
        "S-3",
        "Вектор: руководитель не совпадает с ЕГРЮЛ",
        "vector",
        "«Кредитная линия», 10 млн ₽ на 24 месяца: руководитель в кабинете не тот, что в ЕГРЮЛ → "
        "ручное рассмотрение, андеррайтер снижает лимит до 6 млн → клиент отказывается.",
    )
    s.company("vector")
    s.draft("CREDIT_LINE", "10000000", 24)
    s.document("financial_report")
    s.submit()
    s.card("review", "Карточка: у специалиста", "статус `in_review`, этап «Заявка у специалиста».")
    s.underwriter(
        "uw",
        _uw(
            "counter_offer",
            "Руководитель в ЕГРЮЛ другой: снижаем лимит до подтверждения полномочий",
            amount="6000000",
            term_months=24,
            rate="24",
        ),
        why="Контрпредложение: лимит 6 млн под 24%.",
    )
    s.card("offer", "Карточка: контрпредложение", "статус `offer_ready`, 6 000 000.")
    s.step(
        "decline",
        "Отказаться от предложения",
        "POST",
        "/applications/{application_id}/offer/decline",
        note="200, статус `offer_declined`: заявка закрыта, компания может подать новую.",
        body={"reason": "Нужен лимит 10 млн, подтвердим полномочия и вернёмся"},
    )
    s.finish()


def _s4(collection: Collection, root: str) -> None:
    s = Scenario(
        collection,
        root,
        "S-4",
        "Закат: отказ по стоп-факторам",
        "zakat",
        "«Кредит без залога», 2 млн ₽ на 12 месяцев: компания ликвидируется, просрочка больше "
        "90 дней, недоимка → отказ на шаге «Стоп-факторы», модель не вызывается.",
    )
    s.company("zakat")
    s.draft("UNSECURED", "2000000", 12)
    s.submit()
    s.card(
        "decision",
        "Карточка: отказ",
        "статус `rejected`, `decision_summary.outcome` = `REJECT` и понятная клиенту причина "
        "в `client_explanation`.",
    )
    s.step(
        "process",
        "Процесс по заявке",
        "GET",
        "/processes/{application_id}",
        who="underwriter",
        note="`completed`; `visited_node_ids` кончается на `check_stop_factors`, `reject`, "
        "`calculate_score` не было.",
    )
    s.finish()


def _s5(collection: Collection, root: str) -> None:
    s = Scenario(
        collection,
        root,
        "S-5",
        "Прогресс: запрос выписки, затем андеррайтер",
        "progress",
        "«Кредитная линия», 8 млн ₽ на 24 месяца: заявленная выручка 36 млн, по ФНС — 12 млн → "
        "банк просит выписку → клиент загружает её и отвечает → ручное рассмотрение → андеррайтер "
        "одобряет меньший лимит → клиент подписывает.",
    )
    s.company("progress")
    s.draft("CREDIT_LINE", "8000000", 24)
    s.document("financial_report")
    s.submit()
    s.card(
        "info",
        "Карточка: запрос информации",
        "статус `info_requested`; в `info_requests` открытый запрос, в `requested_documents` — "
        "`bank_statement`.",
    )
    s.document("bank_statement", statement="progress")
    s.step(
        "answer",
        "Ответить на запрос",
        "POST",
        "/applications/{application_id}/info-requests/{info_request_id}/answer",
        params={"info_request_id": s.answer("info", '$.info_requests[?(@.status=="open")].id')},
        note="200: запрос закрыт, заявка возвращается в процесс.",
    )
    s.card("review", "Карточка: у специалиста", "статус `in_review`, этап «Заявка у специалиста».")
    s.underwriter(
        "uw",
        _uw(
            "counter_offer",
            "Выписка подтверждает выручку около 12 млн в год: лимит по фактическим оборотам",
            amount="4000000",
            term_months=24,
            rate="25",
        ),
        why="Контрпредложение: лимит 4 млн под 25%.",
    )
    s.card("offer", "Карточка: предложение", "статус `offer_ready`, 4 000 000.")
    s.accept_and_sign()
    s.disbursed()
    s.finish()


def _s6(collection: Collection, root: str) -> None:
    s = Scenario(
        collection,
        root,
        "S-6",
        "Сбой: бюро кредитных историй недоступно",
        "sboy",
        "«Кредит без залога», 1 млн ₽ на 12 месяцев: БКИ по компании не отвечает → по неполным "
        "данным автоматически не решаем, задача у андеррайтера → он отказывает.",
    )
    s.company("sboy")
    s.draft("UNSECURED", "1000000", 12)
    s.submit()
    s.card(
        "review",
        "Карточка: у специалиста",
        "статус `in_review`, этап «Заявка у специалиста». Источник ждёт повторов, поэтому "
        "решение идёт дольше обычного.",
    )
    s.underwriter(
        "uw",
        _uw(
            "reject",
            "Кредитной истории нет: БКИ недоступно, решение по неполным данным не принимаем",
        ),
        why="Отказ: заявка закрыта.",
    )
    s.card("decision", "Карточка: отказ", "статус `rejected`.")
    s.finish()


def _s7(collection: Collection, root: str) -> None:
    s = Scenario(
        collection,
        root,
        "S-7",
        "Ромашка: бизнес-ипотека всегда у человека",
        "romashka",
        "«Бизнес-ипотека», 30 млн ₽ на 120 месяцев, залог — офис на 50 млн: у ипотеки нет лимита "
        "авторешения → андеррайтер одобряет под 18%, политика возвращает (ниже коридора 23–28%) → "
        "новая задача, одобрение под 23,5% → клиент подписывает.",
    )
    s.company("romashka")
    s.draft(
        "MORTGAGE",
        "30000000",
        120,
        purpose="real_estate",
        collateral={
            "type": "real_estate",
            "description": "Офис, г. Москва, ул. Тверская, д. 10",
            "declared_value": "50000000",
            "owner": "self",
        },
        product_fields={
            "property_address": "г. Москва, ул. Тверская, д. 10",
            "property_type": "office",
            "price": 50000000,
        },
    )
    for document_type in ("financial_report", "purchase_contract", "collateral_documents"):
        s.document(document_type)
    s.submit()
    s.card(
        "review",
        "Карточка: у специалиста",
        "статус `in_review`; процесс `mortgage_v2` прошёл `assess_collateral`.",
    )
    approval = {"amount": "30000000", "term_months": 120}
    s.underwriter(
        "uw1",
        _uw(
            "approve",
            "Залог покрывает сумму с дисконтом, выручка стабильная",
            rate="18",
            **approval,
        ),
        why="18% ниже ставок продукта: политика не пропустит и вернёт заявку андеррайтеру.",
    )
    s.card(
        "again", "Карточка: снова у специалиста", "статус `in_review`: у андеррайтера новая задача."
    )
    s.underwriter(
        "uw2",
        _uw("approve", "Ставка в коридоре продукта", rate="23.5", **approval),
        why="23,5% в коридоре: предложение уходит клиенту.",
    )
    s.card("offer", "Карточка: предложение", "статус `offer_ready`, ставка 23.5.")
    s.accept_and_sign()
    s.disbursed()
    s.finish()


def _s8(collection: Collection, root: str) -> None:
    s = Scenario(
        collection,
        root,
        "S-8",
        "Бухгалтер подаёт, подписывает директор",
        "accountant",
        "Бухгалтер Ромашки подаёт «Кредит без залога» на 3 млн и принимает предложение, но "
        "подписать не может — нет доверенности со scope `sign`, 403 → подписывает директор.",
    )
    s.company("romashka")
    s.draft("UNSECURED", "3000000", 24)
    s.submit()
    s.card(
        "decision",
        "Карточка: решение",
        "статус `offer_ready`; в `my_permissions` бухгалтера нет `sign`.",
    )
    s.step(
        "accept",
        "Принять предложение",
        "POST",
        "/applications/{application_id}/offer/accept",
        note="200: принять бухгалтер может.",
    )
    s.step(
        "contract",
        "Договор глазами бухгалтера",
        "GET",
        "/applications/{application_id}/contract",
        note="200: читать договор бухгалтер может.",
    )
    s.step(
        "sign",
        "Подписать договор (бухгалтер)",
        "POST",
        "/applications/{application_id}/sign",
        note="**403**: без доверенности со scope `sign` подписывает только руководитель.",
        body={"password": var("demo_password"), "offer_hash": s.answer("contract", "$.offer_hash")},
    )
    s.contract_and_sign(who="romashka", suffix="/director")
    s.card("disbursed", "Карточка: выдача", "статус `disbursed`.", who="romashka")
    s.finish()


def _startup_application(s: Scenario) -> None:
    s.draft("STARTUP", "3000000", 36)
    s.document("business_plan")
    s.document("financial_model")
    s.submit()
    s.card(
        "review",
        "Карточка: проектная оценка",
        "статус `in_review`, этап «Проектная оценка»; процесс `startup_v2`.",
    )


def _startup_consents(s: Scenario) -> None:
    s.step(
        "consents",
        "Дать личные согласия",
        "POST",
        "/me/consents",
        note=(
            "201: согласия учредителя на обработку данных и запрос его кредитной истории. Без них "
            "проверка учредителя — 422 `consent_required`."
        ),
        body={"types": ["personal_data", "credit_bureau_personal"]},
    )
    s.step(
        "prescreen",
        "Проверить учредителя",
        "POST",
        "/organizations/{organization_id}/founder-prescreen",
        note="201, `status` = `passed`: личная кредитная история учредителя без просрочек.",
    )


def _s9(collection: Collection, root: str) -> None:
    s = Scenario(
        collection,
        root,
        "S-9",
        "Старт: предскрин учредителя и проектная оценка",
        "start",
        "Стартап без оборотов, «Кредит на запуск бизнеса» 3 млн ₽ на 36 месяцев: вместо "
        "предодобрения — проверка учредителя → заявка с бизнес-планом и финмоделью → проектная "
        "оценка андеррайтером → предложение под 17% → подпись → выдача.",
    )
    s.company("start")
    s.step(
        "dashboard",
        "Главный экран",
        "GET",
        "/bff/dashboard",
        query={"organization_id": var("organization_id")},
        note="`organization.segment` = `startup`, предодобрений нет: вместо них блок `startup`.",
    )
    _startup_consents(s)
    s.step(
        "recommend",
        "Подбор продукта",
        "GET",
        "/bff/products/recommend",
        query={
            "organization_id": var("organization_id"),
            "purpose": "working_capital",
            "amount": "3000000",
            "term_months": "36",
        },
        note="Стартапу подходит только `STARTUP`.",
    )
    _startup_application(s)
    s.underwriter(
        "uw",
        _uw(
            "approve",
            "Бизнес-план реалистичный, учредитель без просрочек, программа МСП",
            amount="3000000",
            term_months=36,
            rate="17",
            business_plan="acceptable",
            collateral="поручительство учредителя",
            support_program=True,
        ),
        why="Задача `project_assessment`: в форме ещё оценка бизнес-плана и программа поддержки.",
    )
    s.card("offer", "Карточка: предложение", "статус `offer_ready`, ставка 17.")
    s.accept_and_sign()
    s.disbursed()
    s.finish()


def _s10(collection: Collection, root: str) -> None:
    s = Scenario(
        collection,
        root,
        "S-10",
        "Старт: бизнес-план в кабинете и предодобрение",
        "start",
        "Путь стартапа по целевой схеме: проверка учредителя → бизнес-план и финмодель "
        "в кабинете → оценка проекта → «предодобрено до 3,81 млн» → заявка → андеррайтер "
        "подтверждает предзаполненную оценку → предложение → подпись → выдача.",
    )
    s.company("start")
    _startup_consents(s)
    s.step(
        "plan",
        "Сохранить бизнес-план",
        "PUT",
        "/organizations/{organization_id}/business-plan",
        note="201 — первая версия, 200 — новая ревизия: кофейня, выручка 1 млн и расходы 800 тыс. "
        "в месяц, гарантия Корпорации МСП на половину кредита.",
        body=startup_plan(),
    )
    s.step(
        "assessment",
        "Оценить проект",
        "POST",
        "/organizations/{organization_id}/project-assessment",
        note="201, `passed`, `product_code` = `STARTUP`, `max_amount` = 3 810 000: поток "
        "выдерживает платёж при DSCR 1,3 по верхней ставке коридора.",
    )
    s.step(
        "dashboard",
        "Главный экран: предодобрение",
        "GET",
        "/bff/dashboard",
        query={"organization_id": var("organization_id")},
        note="В `pre_approved` — STARTUP до 3 810 000, в ленте событие о предодобрении. "
        "Если пусто — проект ещё оценивается, отправьте ещё раз.",
    )
    s.step(
        "offers",
        "Предодобренные предложения",
        "GET",
        "/organizations/{organization_id}/pre-approved-offers",
        note="Одно предложение, `basis` = `project`.",
    )
    _startup_application(s)
    s.underwriter(
        "uw",
        _uw(
            "approve",
            "Проект подтверждаю: финмодель реалистичная, гарантия Корпорации МСП",
            amount="3000000",
            term_months=36,
            rate="17",
            business_plan="acceptable",
            collateral="Поручительство учредителя",
            support_program=True,
        ),
        why="Форма предзаполнена оценкой проекта (`startup.form` в карточке андеррайтера): "
        "андеррайтер подтверждает её и ставит ставку.",
    )
    s.card("offer", "Карточка: предложение", "статус `offer_ready`, 3 000 000 под 17%.")
    s.accept_and_sign()
    s.disbursed()
    s.finish()
