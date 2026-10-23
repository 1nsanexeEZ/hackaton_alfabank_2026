# Модуль `applications`

## Зачем

Кредитная заявка от черновика до выдачи. Клиент заводит черновик на компанию и продукт, заполняет
его (автосохранение), прикладывает документы, подаёт, отвечает на запросы банка, принимает или
отклоняет предложение и подписывает договор. Движок процесса шлёт заявке команды (начать проверку,
запросить данные, предложение, отказ, выдача). Модуль — единственный владелец бизнес-статуса
заявки: переходы — в [state-machine.md](../state-machine.md). Код — `backend/src/modules/applications`.

## Структура

Раскладка по слоям из [settings/04-module-structure.md](../../settings/04-module-structure.md).

```
applications/
├── facade.py                 # ApplicationsFacade + реэкспорт DTO и Literal-типов для соседей;
│                             # реализация — infrastructure/adapters/applications_facade.py
├── module.py                 # register: роутер; wire: хранилище документов, ЭДО, АБС, фасад;
│                             # startup/shutdown: бакет и фоновая задача истечения предложений
├── domain/
│   ├── application.py        # агрегат CreditApplication: все переходы статуса
│   ├── entities.py           # Document, InfoRequest — меняются только через агрегат
│   ├── value_objects.py      # номер, запрос, условия продукта, залог, оффер, подпись, выдача…
│   ├── fields_schema.py      # схема продуктовых полей заявки
│   ├── statuses.py           # таблица переходов TRANSITIONS, FINAL/ACTIVE_STATUSES
│   ├── actions.py            # какие кнопки доступны: статус + права внутри компании
│   ├── events.py             # доменные события заявки
│   └── enums.py              # ApplicationStatus, DocumentStatus, InfoRequestStatus
├── application/
│   ├── dto/                  # applications (фасад), drafts (автосохранение, UNSET),
│   │                         # views (ответы API), common (UNSET)
│   ├── interfaces/           # repositories, storage (DocumentStorage), edo (EdoClient),
│   │                         # abs (AbsClient), outbox (MessageOutbox),
│   │                         # transactions (ApplicationTransaction для фоновой задачи)
│   ├── mappers/              # dto: домен ↔ DTO (свои и соседей); messages: события → контракты,
│   │                         # команды процесса → оффер и решение
│   └── use_cases/            # applications (чтение для API), drafts, documents, submission,
│                             # offers, contracts (договор и подпись), commands (команды процесса,
│                             # метка этапа, истечение оффера), expiry (фоновая задача),
│                             # cards (фасад); common — доступ, сохранение с событиями, экран заявки
├── infrastructure/
│   ├── adapters/             # applications_facade, document_storage (MinIO), edo_client, abs_client,
│   │                         # application_unit_of_work, application_transaction
│   ├── config.py             # ApplicationsSettings (APPLICATIONS_*)
│   ├── database/             # models
│   └── repositories/         # applications, mappers
└── presentation/
    ├── api/                  # applications — один роутер /applications
    ├── schemas/              # applications, documents, contracts
    ├── consumers.py          # команды процесса и метки этапа из process.events
    ├── expiry.py             # фоновая задача: просроченные предложения → EXPIRED
    └── dependencies.py       # сборка use case'ов для роутера, обработчиков, задачи и фасада
```

- **Внешние системы — за портами.** Хранилище документов (MinIO, S3 API), ЭДО и АБС use case'ы
  получают через `DocumentStorage`, `EdoClient`, `AbsClient`. Пока не задан
  `APPLICATIONS_EXTERNAL_MOCKS_URL`, подпись и выдача идут через `SimulatedEdoClient` и
  `SimulatedAbsClient`, ответы помечены `simulated: true`.
- **Use case возвращает DTO.** Схемы ответа собираются через `model_validate(dto)` с
  `from_attributes=True`; белый список полей для клиента — по-прежнему pydantic-схемы.
- **Автосохранение черновика.** `ApplicationUpdate.to_dto()` отличает «не прислали» (`UNSET`) от
  `null`: `collateral: null` убирает залог, `consents: null` снимает оба согласия. Значения
  проверяются в начале use case'а, до проверки доступа.
- Своих HTTP-исключений нет: агрегат и use case'ы бросают исключения core (`NotFoundError`,
  `ConflictError`, `ValidationError`, `InvalidStatusTransitionError`…), их переводит общий
  обработчик, поэтому `infrastructure/exception_handler.py` не заведён.

## Транзакции

| Где | Кто коммитит |
|---|---|
| HTTP | use case через `UnitOfWork`: заявка, история и исходящие события — одной транзакцией. `ApplicationUnitOfWork` переводит отказ базы в `409`: заявку успел поменять кто-то другой (`StaleDataError`) — `version_conflict`; у компании уже есть активная заявка на продукт (уникальный индекс) — `duplicate_active` |
| Kafka-обработчики (`consumers.py`) | ядро: `MessageProcessor` коммитит заявку и события вместе с отметкой инбокса. `HandleCommandUseCase` и `SetClientStageUseCase` не коммитят |
| Фоновая задача истечения | `ExpireOffersUseCase`: на каждую заявку своя `ApplicationTransaction` (своя сессия). Если клиент в это время принял предложение, транзакция откатывается (`StaleApplicationError`), заявка пропускается |

Подпись: сначала ответ ЭДО (вне транзакции), потом заявка, данные подписи (IP, user-agent, номер
документа ЭДО) и событие — одной транзакцией. Выдача: вызов АБС вне транзакции, ключ идемпотентности
на стороне АБС — id заявки.

## API

Права — `requests.read` / `requests.create` / `requests.update`; клиент видит только заявки своих
компаний (политика `org_member`, чужая — 404), действия внутри компании проверяет `clients`
(`submit_application`, `sign`).

| Метод | Путь | Что |
|---|---|---|
| POST | `/applications` | черновик на компанию и продукт, реквизиты — из данных банка |
| GET | `/applications` | список: `organization_id`, `status`, `limit`, `offset` |
| GET | `/applications/{id}` | заявка с `available_actions` и `my_permissions` |
| PATCH | `/applications/{id}` | автосохранение черновика по `version` |
| GET | `/applications/{id}/completeness` | чего не хватает для подачи |
| POST | `/applications/{id}/documents` | объявить файл → presigned URL для загрузки |
| POST | `/applications/{id}/documents/{document_id}/confirm` | файл дошёл до хранилища |
| GET | `/applications/{id}/documents/{document_id}/download` | presigned URL на скачивание |
| DELETE | `/applications/{id}/documents/{document_id}` | убрать документ |
| POST | `/applications/{id}/submit` | подать: снимок компании замораживается в заявке |
| POST | `/applications/{id}/info-requests/{info_request_id}/answer` | ответить на запрос банка |
| POST | `/applications/{id}/offer/accept`, `/offer/decline` | принять или отклонить предложение |
| GET | `/applications/{id}/contract` | договор: заёмщик, условия, график, подписанты, `offer_hash` |
| POST | `/applications/{id}/sign` | подпись: пароль ещё раз и `offer_hash` из договора |
| POST | `/applications/{id}/cancel` | отозвать заявку |

## Kafka

| Топик | Группа | Что делает |
|---|---|---|
| `applications.commands` | `applications.commands` | команды движка: `StartReview`, `RequestInfo`, `PresentOffer`, `RejectApplication`, `MarkDisbursed`. Команда, которая не подходит к статусу, подтверждается без изменений |
| `process.events` | `applications.process-events` | `StepCompleted` — метка этапа для клиента (`client_stage`), пишется мимо версии агрегата |

События заявки (`applications.events`) уходят через outbox той же транзакции.

## Фасад

`ApplicationsFacade`: `get_card`, `get_completeness`, `get_scoring_input`, `list_for_organization`,
`list_documents`, `read_document`. Читают `process`, `scoring`, `decision`, `enrichment`, `projector`,
`notifications`, `bff`; проверок доступа в фасаде нет — вызывает доверенный код.
