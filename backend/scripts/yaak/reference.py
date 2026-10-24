"""The reference folder: every operation of the OpenAPI schema, grouped by area.

A request carries the token of a role that may call it, an example body and
path parameters taken from the latest answers: the newest application of
«Ромашка», the companies by INN, an account and a role the admin requests
create for themselves, so trying them does not break the demo data.
"""

from pathlib import Path
from typing import Any

from scripts.yaak.accounts import ACCOUNTS, INN, token
from scripts.yaak.collection import NO_AUTH, Collection, Raw, answer, bearer, model_id, var

# key, name, description; operations go to the first folder whose test matches
FOLDERS: list[tuple[str, str, str]] = [
    ("service", "Служебные", "Живость и готовность сервиса."),
    ("auth", "Вход", "Токен по паролю или демо-вход, публичные ключи JWT."),
    ("me", "Профиль и согласия", "Профиль представителя и его личные согласия (152-ФЗ)."),
    ("organizations", "Компании", "Компании, участники, доверенности, отчётность, согласия."),
    (
        "products",
        "Продукты",
        "Каталог, подбор по потребности, калькулятор, применимость; ведение каталога.",
    ),
    ("applications", "Заявки", "Черновик, документы, подача, предложение, договор, подпись."),
    ("process", "Процесс и задачи", "BPMN-процессы и задачи андеррайтера."),
    ("decision", "Предодобрение и стартапы", "Предодобрения, проверка учредителя, проект."),
    ("feed", "Лента и новости", "События по заявкам, поток SSE, персональные новости."),
    ("bff", "BFF клиента", "Экраны кабинета клиента одним запросом."),
    ("backoffice", "BFF бэк-офиса", "Очередь, карточка андеррайтера, метрики."),
    ("admin", "Администрирование", "Аккаунты и роли: создаём свои и на них пробуем."),
]

NAMES: dict[str, str] = {
    "POST /auth/login": "Вход по паролю",
    "POST /auth/demo-login": "Демо-вход без пароля",
    "GET /auth/demo-accounts": "Демо-аккаунты",
    "GET /.well-known/jwks.json": "Публичные ключи JWT",
    "GET /me": "Мой профиль",
    "PATCH /me/profile": "Изменить профиль",
    "GET /me/consents": "Мои согласия",
    "POST /me/consents": "Дать согласия",
    "DELETE /me/consents/{type}": "Отозвать согласие",
    "GET /organizations/{organization_id}/consents": "Согласия компании",
    "POST /organizations/{organization_id}/consents": "Дать согласие компании",
    "DELETE /organizations/{organization_id}/consents/{type}": "Отозвать согласие компании",
    "GET /accounts": "Аккаунты",
    "POST /accounts": "Создать аккаунт",
    "GET /accounts/{account_id}": "Аккаунт",
    "PATCH /accounts/{account_id}": "Изменить аккаунт",
    "DELETE /accounts/{account_id}": "Удалить аккаунт",
    "GET /roles": "Роли",
    "POST /roles": "Создать роль",
    "GET /roles/{role_id}": "Роль",
    "PATCH /roles/{role_id}": "Изменить роль",
    "DELETE /roles/{role_id}": "Удалить роль",
    "GET /products": "Каталог продуктов",
    "POST /products": "Добавить продукт",
    "GET /products/all": "Все продукты с черновиками и архивом",
    "POST /products/recommend": "Подбор по потребности",
    "POST /products/recommend/{organization_id}": "Подбор для компании",
    "GET /products/{code}": "Продукт",
    "PUT /products/{code}": "Новые условия продукта",
    "DELETE /products/{code}": "Снять продукт с продажи",
    "POST /products/{code}/activate": "Опубликовать черновик",
    "POST /products/{code}/calculate": "Калькулятор платежей",
    "GET /products/{code}/eligibility": "Подходит ли продукт компании",
    "GET /organizations": "Компании",
    "GET /organizations/{organization_id}": "Карточка компании",
    "POST /organizations/{organization_id}/verification": "Сверить с реестрами",
    "GET /organizations/{organization_id}/members": "Участники компании",
    "POST /organizations/{organization_id}/members": "Добавить участника",
    "PATCH /organizations/{organization_id}/members/{account_id}": "Сменить роль участника",
    "DELETE /organizations/{organization_id}/members/{account_id}": "Убрать участника",
    "POST /organizations/{organization_id}/members/{account_id}/poa": "Выдать доверенность",
    "GET /organizations/{organization_id}/financial-reports": "Финансовая отчётность",
    "POST /organizations/{organization_id}/financial-reports": "Подать отчётность",
    "GET /organizations/{organization_id}/business-plan": "Бизнес-план стартапа",
    "PUT /organizations/{organization_id}/business-plan": "Сохранить бизнес-план",
    "POST /applications": "Создать черновик заявки",
    "GET /applications": "Мои заявки",
    "GET /applications/{application_id}": "Карточка заявки",
    "PATCH /applications/{application_id}": "Заполнить черновик",
    "GET /applications/{application_id}/completeness": "Чего не хватает для подачи",
    "POST /applications/{application_id}/documents": "Заявить документ",
    "POST /applications/{application_id}/documents/{document_id}/confirm": "Подтвердить загрузку",
    "GET /applications/{application_id}/documents/{document_id}/download": "Скачать документ",
    "DELETE /applications/{application_id}/documents/{document_id}": "Удалить документ",
    "POST /applications/{application_id}/submit": "Подать заявку",
    "POST /applications/{application_id}/info-requests/{info_request_id}/answer": (
        "Ответить на запрос информации"
    ),
    "POST /applications/{application_id}/offer/accept": "Принять предложение",
    "POST /applications/{application_id}/offer/decline": "Отказаться от предложения",
    "GET /applications/{application_id}/contract": "Договор перед подписанием",
    "POST /applications/{application_id}/sign": "Подписать договор",
    "POST /applications/{application_id}/cancel": "Отменить заявку",
    "GET /tasks": "Очередь задач",
    "GET /tasks/{task_id}": "Задача",
    "POST /tasks/{task_id}/claim": "Взять задачу",
    "POST /tasks/{task_id}/complete": "Закрыть задачу решением",
    "GET /processes/{application_id}": "Процесс по заявке",
    "GET /workflows": "BPMN-процессы",
    "GET /workflows/{code}/diagram": "BPMN-схема процесса",
    "GET /organizations/{organization_id}/pre-approved-offers": "Предодобренные предложения",
    "POST /organizations/{organization_id}/founder-prescreen": "Проверить учредителя",
    "GET /organizations/{organization_id}/founder-prescreen": "Результат проверки учредителя",
    "POST /organizations/{organization_id}/project-assessment": "Оценить проект стартапа",
    "GET /organizations/{organization_id}/project-assessment": "Результат оценки проекта",
    "GET /feed": "Лента событий",
    "GET /feed/unread-count": "Непрочитанные события",
    "POST /feed/read-all": "Прочитать все события",
    "POST /feed/stream-ticket": "Билет на поток событий",
    "GET /feed/stream": "Поток событий (SSE)",
    "POST /feed/{item_id}/read": "Прочитать событие",
    "GET /news": "Новости для компании",
    "POST /news/{news_id}/read": "Прочитать новость",
    "GET /bff/dashboard": "Главный экран клиента",
    "GET /bff/applications": "Заявки компании",
    "GET /bff/applications/{application_id}": "Карточка заявки для клиента",
    "GET /bff/products/recommend": "Подбор с предодобрением",
    "POST /bff/products/{code}/calculate": "Калькулятор по предодобренной ставке",
    "GET /bff/backoffice/queue": "Очередь андеррайтера",
    "GET /bff/backoffice/applications/{application_id}": "Карточка андеррайтера",
    "GET /bff/backoffice/metrics": "Метрики бэк-офиса",
    "GET /health": "Сервис жив",
    "GET /ready": "Сервис готов (БД, Kafka)",
}

# Operations of the startup: they need «Старт», not «Ромашка».
_STARTUP_PATHS = ("/business-plan", "/founder-prescreen", "/project-assessment")
# Keeping the catalog: the admin works on a product of its own, the demo catalog stays.
_CATALOG_KEEPING = {
    ("get", "/products/all"),
    ("post", "/products"),
    ("put", "/products/{code}"),
    ("delete", "/products/{code}"),
    ("post", "/products/{code}/activate"),
}
YAAK_PRODUCT = "YAAK_DEMO"
# Changes the demo data in a way the scenarios notice.
_CAREFUL = (
    "Меняет демо-данные: после этого запроса сценарии могут вести себя иначе, "
    "вернуть всё — пересоздать базу (`docker compose down -v`)."
)

_OFFER = (
    "Работает, когда предложение готово (`offer_ready`): овердрафт Ромашки банк одобряет сам "
    "через пару секунд после подачи."
)
_TASK = (
    "Первая задача очереди. Очередь пуста — пройдите сценарий до шага «у специалиста» "
    "(S-2, S-3, S-5, S-6, S-7)."
)

NOTES: dict[str, str] = {
    "GET /organizations": (
        "Под андеррайтером: банк видит все компании. Отсюда переменные справочника "
        "`organization_id` (Ромашка) и `startup_organization_id` (Старт)."
    ),
    "GET /applications": "Отсюда `application_id` справочника: самая новая заявка Ромашки.",
    "POST /accounts": "Создаёт свой аккаунт: следующие запросы папки работают с ним.",
    "POST /roles": "Создаёт свою роль: следующие запросы папки работают с ней.",
    "POST /products": (
        f"Создаёт черновик `{YAAK_PRODUCT}`: правка, публикация и снятие с продажи работают "
        "с ним, демо-каталог не меняется. Повторный запуск — 409: код уже занят."
    ),
    "PUT /products/{code}": (
        f"Черновик `{YAAK_PRODUCT}` меняется на месте; опубликованный или архивный продукт "
        "получает новую активную версию."
    ),
    "DELETE /products/{code}": (
        f"Опубликованный `{YAAK_PRODUCT}` уходит в архив, черновик удаляется."
    ),
    "POST /organizations/{organization_id}/members": (
        "Добавляет ИП Иванова в Ромашку сотрудником: смена роли, доверенность и удаление — "
        "над ним, бухгалтер Ромашки остаётся на месте."
    ),
    "DELETE /me/consents/{type}": _CAREFUL,
    "DELETE /organizations/{organization_id}/consents/{type}": _CAREFUL,
    "POST /applications": (
        "Черновик овердрафта Ромашки: продукта нет в сценариях, S-1, S-7 и S-8 он не задевает. "
        "Дальше папка работает с ним как с самой новой заявкой: выписка, подача, предложение."
    ),
    "POST /applications/{application_id}/info-requests/{info_request_id}/answer": (
        "Работает, когда у заявки открыт запрос информации (`info_requested`), как в S-5."
    ),
    "POST /applications/{application_id}/offer/accept": _OFFER,
    "POST /applications/{application_id}/offer/decline": _OFFER,
    "DELETE /applications/{application_id}/documents/{document_id}": (
        "Удалить документ можно, пока заявка — черновик: создайте черновик и заявите документ."
    ),
    "GET /applications/{application_id}/contract": "Появляется, когда предложение принято.",
    "POST /applications/{application_id}/sign": "Работает после «Принять предложение».",
    "POST /applications/{application_id}/cancel": (
        "Закрывает заявку: отменить можно черновик, поданную заявку, запрос информации "
        "и готовое предложение, но не заявку у андеррайтера."
    ),
    "GET /tasks/{task_id}": _TASK,
    "POST /tasks/{task_id}/claim": _TASK,
    "POST /tasks/{task_id}/complete": f"{_TASK} {_CAREFUL}",
    "GET /feed/stream": (
        "Поток не заканчивается сам: остановите запрос, когда насмотритесь. Билет одноразовый, "
        "новый берётся при каждой отправке."
    ),
}

_STARTUP_PLAN: dict[str, Any] = {
    "summary": "Кофейня у метро: зерно от обжарщика, завтраки, доставка по району",
    "financial_model": {
        "months": [{"revenue": "1000000", "expenses": "800000"}] * 24,
        "own_funds": "1000000",
        "collateral_description": "Поручительство учредителя",
        "guarantee": "msp_corporation",
        "guarantee_share": "0.5",
        "loan_amount": "3000000",
        "loan_term_months": 36,
    },
}


def startup_plan() -> dict[str, Any]:
    return _STARTUP_PLAN


_PRODUCT_TERMS: dict[str, Any] = {
    "frontend_id": "yaak-demo",
    "name": "Факторинг (Yaak)",
    "short_description": "Продукт из коллекции Yaak: деньги под отсрочку платежа покупателей",
    "purposes": ["working_capital", "cash_gap"],
    "facility": "credit_line_revolving",
    "repayment_options": ["interest_only", "annuity"],
    "amount_min": "500000",
    "amount_max": "20000000",
    "term_min_months": 3,
    "term_max_months": 12,
    "rate_base": "21",
    "rate_max": "27",
    "min_business_age_months": 6,
    "min_annual_revenue": "5000000",
    "required_documents": [
        {"type": "receivables_register", "title": "Реестр дебиторской задолженности"}
    ],
    "workflow_code": "standard_v2",
    "auto_decision_limit": "5000000",
}


PDF_STUB = "%PDF-1.4 demo"
STATEMENTS = Path(__file__).resolve().parents[2] / "seed" / "statements"


def statement_csv(name: str) -> str:
    """A synthetic bank statement of the seed, with the same bytes on every platform: git may
    check the file out with CRLF."""
    return (STATEMENTS / f"{name}.csv").read_text(encoding="utf-8").replace("\r\n", "\n")


def ref(method: str, path: str) -> str:
    return model_id("rq", f"reference/{method.upper()} {path}")


def _bodies() -> dict[str, Any]:
    application = "/applications/{application_id}"
    return {
        "POST /auth/login": {"login": ACCOUNTS["romashka"][0], "password": var("demo_password")},
        "POST /auth/demo-login": {"login": ACCOUNTS["romashka"][0]},
        "PATCH /me/profile": {"position": "Генеральный директор"},
        "POST /me/consents": {"types": ["personal_data", "credit_bureau_personal"]},
        "POST /organizations/{organization_id}/consents": {"types": ["credit_bureau_company"]},
        "POST /accounts": {
            "email": "yaak-" + var("uuid.v4()") + "@example.com",
            "password": "Yaak-2026!",
            "role_id": answer(ref("GET", "/roles"), '$[?(@.name=="client")].id'),
            "profile": {"last_name": "Проверкин", "first_name": "Яков", "position": "Менеджер"},
        },
        "PATCH /accounts/{account_id}": {"profile": {"position": "Старший менеджер"}},
        "POST /roles": {
            "name": "yaak-" + var("uuid.v4()"),
            "description": "Роль из коллекции Yaak",
            "permissions": ["feed.read", "requests.read"],
            "policies": {"requests.read": ["own_only"]},
        },
        "PATCH /roles/{role_id}": {"description": "Роль из коллекции Yaak, изменена"},
        "POST /products/recommend": {
            "purpose": "working_capital",
            "amount": "3000000",
            "term_months": 24,
        },
        "POST /products/recommend/{organization_id}": {
            "purpose": "working_capital",
            "amount": "3000000",
            "term_months": 24,
        },
        "POST /products/{code}/calculate": {"amount": "3000000", "term_months": 24},
        "POST /products": {"code": YAAK_PRODUCT, **_PRODUCT_TERMS},
        "PUT /products/{code}": _PRODUCT_TERMS | {"rate_base": "20"},
        "POST /organizations/{organization_id}/members": {
            "login": ACCOUNTS["ivanov"][0],
            "role": "employee",
        },
        "PATCH /organizations/{organization_id}/members/{account_id}": {"role": "accountant"},
        "POST /organizations/{organization_id}/members/{account_id}/poa": {
            "number": "77 АА 0000001",
            "issued_at": "2026-10-01",
            "valid_until": "2027-10-01",
            "scope": ["submit_application"],
        },
        "POST /organizations/{organization_id}/financial-reports": {
            "period_year": 2025,
            "revenue": "48000000",
            "expenses": "41000000",
            "net_profit": "5600000",
            "total_liabilities": "12000000",
            "monthly_debt_payments": "350000",
        },
        "PUT /organizations/{organization_id}/business-plan": startup_plan(),
        "POST /applications": {
            "organization_id": var("organization_id"),
            "product_code": "OVERDRAFT",
        },
        f"PATCH {application}": {
            "version": Raw(answer(ref("GET", application), "$.version", behavior="always")),
            "request": {"amount": "1000000", "term_months": 12, "purpose": "cash_gap"},
            "consents": {"personal_data": True, "credit_bureau": True},
            "beneficiary": {"acts_for_third_party": False},
        },
        f"POST {application}/documents": {
            "type": "bank_statement",
            "filename": "romashka.csv",
            "content_type": "text/csv",
            "size_bytes": len(statement_csv("romashka").encode()),
        },
        f"POST {application}/offer/decline": {"reason": "Нашли другое финансирование"},
        f"POST {application}/sign": {
            "password": var("demo_password"),
            "offer_hash": answer(ref("GET", f"{application}/contract"), "$.offer_hash"),
        },
        f"POST {application}/cancel": {"reason": "Передумали"},
        "POST /tasks/{task_id}/complete": {
            "decision": "approve",
            "amount": "3000000",
            "term_months": 24,
            "rate": "24",
            "comment": "Решение из справочника коллекции",
        },
        "POST /bff/products/{code}/calculate": {"amount": "3000000", "term_months": 24},
    }


def reference_variables() -> dict[str, str]:
    companies = ref("GET", "/organizations")
    application = ref("GET", "/applications/{application_id}")
    return {
        "organization_id": answer(companies, f'$[?(@.inn=="{INN["romashka"]}")].id'),
        "startup_organization_id": answer(companies, f'$[?(@.inn=="{INN["start"]}")].id'),
        "application_id": answer(ref("GET", "/applications"), "$[0].id"),
        "document_id": answer(
            ref("POST", "/applications/{application_id}/documents"), "$.document.id"
        ),
        "info_request_id": answer(
            application, '$.info_requests[?(@.status=="open")].id', behavior="always"
        ),
        "task_id": answer(ref("GET", "/tasks"), "$[0].id"),
        "new_account_id": answer(ref("POST", "/accounts"), "$.id"),
        "new_role_id": answer(ref("POST", "/roles"), "$.id"),
        "member_account_id": answer(
            ref("POST", "/organizations/{organization_id}/members"), "$.account_id"
        ),
        "feed_item_id": answer(ref("GET", "/feed"), "$.items[0].id"),
        "news_id": answer(ref("GET", "/news"), "$[0].id"),
        "workflow_code": answer(ref("GET", "/workflows"), "$[0].code"),
    }


def _role(method: str, path: str, operation: dict[str, Any]) -> str | None:
    if not operation.get("security"):
        return None
    if path.startswith(("/accounts", "/roles")) or (method, path) in _CATALOG_KEEPING:
        return "admin"
    if path.startswith(("/tasks", "/processes", "/workflows", "/bff/backoffice")):
        return "underwriter"
    if (method, path) == ("get", "/organizations"):
        return "underwriter"
    if path.endswith(_STARTUP_PATHS):
        return "start"
    return "romashka"


def _folder(path: str, tags: list[str]) -> str:
    if path.startswith("/bff/backoffice"):
        return "backoffice"
    if path.startswith(("/accounts", "/roles")):
        return "admin"
    if tags[0] == "news":
        return "feed"
    return tags[0]


def _path_value(method: str, path: str, param: str) -> str:
    if param == "organization_id":
        return var("startup_organization_id" if path.endswith(_STARTUP_PATHS) else param)
    if param == "account_id":
        return var("new_account_id" if path.startswith("/accounts") else "member_account_id")
    if param == "role_id":
        return var("new_role_id")
    if param == "item_id":
        return var("feed_item_id")
    if param == "code":
        if path.startswith("/workflows"):
            return var("workflow_code")
        return YAAK_PRODUCT if (method, path) in _CATALOG_KEEPING else "UNSECURED"
    if param == "type":
        return "credit_bureau_company" if path.startswith("/organizations") else "personal_data"
    return var(param)


_QUERY_VALUES = {
    "organization_id": var("organization_id"),
    "purpose": "working_capital",
    "amount": "3000000",
    "term_months": "24",
    "limit": "20",
    "offset": "0",
    "ticket": answer(ref("POST", "/feed/stream-ticket"), "$.ticket", behavior="always"),
}


def _query_params(operation: dict[str, Any]) -> list[tuple[str, str, bool]]:
    params = []
    for parameter in operation.get("parameters", []):
        if parameter["in"] != "query":
            continue
        name = parameter["name"]
        schema = parameter.get("schema", {})
        options = [s for s in schema.get("anyOf", [schema]) if s.get("type") != "null"]
        enum = next((s["enum"] for s in options if "enum" in s), None)
        value = _QUERY_VALUES.get(name) or (enum[0] if enum else str(schema.get("default") or ""))
        params.append((name, value, bool(parameter.get("required"))))
    return params


def url_of(path: str) -> tuple[str, list[str]]:
    """`/a/{x}/b` → `${[ base_url ]}/a/:x/b` and the names of the path parameters."""
    names = []
    parts = []
    for part in path.split("/"):
        if part.startswith("{") and part.endswith("}"):
            names.append(part[1:-1])
            parts.append(f":{part[1:-1]}")
        else:
            parts.append(part)
    return var("base_url") + "/".join(parts), names


def add_reference(collection: Collection, openapi: dict[str, Any]) -> None:
    root = collection.folder(
        "reference",
        "Справочник API",
        parent=None,
        description=(
            "Все ручки API по разделам. Каждый запрос идёт с токеном роли, которой он доступен; "
            "id в пути берутся из последних ответов (переменные папки)."
        ),
    )
    collection.environment(
        "reference",
        "Переменные справочника",
        reference_variables(),
        parent_model="folder",
        parent_id=root,
    )
    folders = {
        key: collection.folder(f"reference/{key}", name, parent=root, description=description)
        for key, name, description in FOLDERS
    }
    bodies = _bodies()
    operations = [
        (method, path, operation)
        for path, by_method in openapi["paths"].items()
        for method, operation in by_method.items()
    ]
    # Deleting goes last in its folder: the requests before it still have something to work on.
    operations.sort(key=lambda item: item[0] == "delete")
    for method, path, operation in operations:
        key = f"{method.upper()} {path}"
        url, names = url_of(path)
        role = _role(method, path, operation)
        description = (operation.get("description") or operation.get("summary") or "").strip()
        if key in NOTES:
            description += f"\n\n{NOTES[key]}"
        if role is not None:
            description += f"\n\nТокен: {ACCOUNTS[role][1]}."
        collection.request(
            ref(method, path),
            NAMES.get(key, operation.get("summary", key)),
            method.upper(),
            url,
            folder=folders[_folder(path, operation.get("tags") or ["service"])],
            auth=bearer(token(role)) if role else NO_AUTH,
            description=description.strip(),
            params=[(f":{name}", _path_value(method, path, name), True) for name in names]
            + _query_params(operation),
            body=bodies.get(key, _empty_body(operation)),
        )
        if key == "POST /applications/{application_id}/documents":
            collection.request(
                model_id("rq", "reference/upload"),
                "Загрузить файл по presigned URL",
                "PUT",
                answer(ref(method, path), "$.upload.url"),
                folder=folders["applications"],
                auth=NO_AUTH,
                description=(
                    "Файл идёт прямо в хранилище (MinIO через nginx) по ссылке из ответа "
                    "«Заявить документ», без токена: выписка Ромашки из сидов."
                ),
                body=statement_csv("romashka"),
                content_type="text/csv",
            )


def _empty_body(operation: dict[str, Any]) -> Any:
    """A required body with no example gets `{}`: the 422 tells what it misses."""
    body = operation.get("requestBody")
    return {} if body and body.get("required") else None
