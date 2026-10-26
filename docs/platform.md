# Платформа бэкенда

Общая часть, на которой стоят все модули: устройство модуля, чтение соседей через фасады, Kafka (outbox/inbox), доступ `org_member`, тесты. Код — `backend/src/core`, сборка приложения — `backend/src/main.py`.

## Модуль

```
backend/src/modules/<module>/
├── facade.py         Protocol + frozen DTO — всё, что модуль отдаёт соседям
├── module.py         register(app) — роутеры; wire(app) — реализации фасадов; subscribers() — подписки Kafka
├── domain/           чистый Python: сущности, правила, доменные события и исключения
├── application/      dto/, interfaces/ (Protocol), use_cases/ (класс на операцию)
├── infrastructure/   adapters/, database/ (ORM, таблицы с префиксом модуля), repositories/, exception_handler.py
└── presentation/     api/ (роутеры), schemas/ (pydantic), consumers.py (Kafka), dependencies.py
```

Подробно, со слоями и чек-листом перевода старых модулей, — [`settings/04-module-structure.md`](../settings/04-module-structure.md). Эталоны — `identity` (HTTP API) и `enrichment` (команды из Kafka, внешние HTTP-источники). На эту структуру переведены все модули, кроме `products`, `scoring` и `decision`: они держат роутеры в `api/`, порты в `application/ports.py`, ORM-модели в `infrastructure/models.py`.

`main.py` содержит явный список модулей и вызывает `register`, затем `wire`; подписки всех модулей отдаёт брокеру. Новые таблицы модуль добавляет импортом своих ORM-моделей (`infrastructure.database.models`, в `products`, `scoring`, `decision` — `infrastructure.models`) в `src/models.py` (его читают Alembic и тесты).

Границы проверяет import-linter (`uv run lint-imports`, контракты в `pyproject.toml`):
- `domain` не импортирует FastAPI, Starlette, SQLAlchemy, Pydantic, httpx, FastStream, aiokafka, aioboto3;
- `domain` не импортирует `application`; `domain` и `application` не импортируют `infrastructure`, `presentation` (`api`), `module` и сиды (`seed`);
- `infrastructure` не импортирует `presentation` (`api`) и `module`;
- в переведённых модулях (все, кроме `products`, `scoring`, `decision`) порядок слоёв проверяется целиком: `module` → `presentation` → `infrastructure` → `facade` → `application` → `domain`;
- модуль читает другой модуль только через его `facade.py`;
- `src.core` не знает о модулях.

## Фасады

Реализацию фасада владелец регистрирует в `wire(app)`; фабрика получает сессию вызывающего, поэтому вызов фасада идёт в его транзакции:

```python
# src/modules/clients/module.py
def wire(app: FastAPI) -> None:
    app.state.facades.register(ClientsFacade, ClientsFacadeImpl)
    app.state.facades.register(MemberOrganizationsResolver, ClientsFacadeImpl)

# в роутере соседа
clients: Annotated[ClientsFacade, Depends(use_facade(ClientsFacade))]

# в обработчике Kafka
clients = ctx.facade(ClientsFacade)
```

Незарегистрированный фасад — `FacadeNotRegisteredError` с подсказкой, какой модуль должен его подключить.

## Kafka

| Что | Где |
|---|---|
| 13 топиков и DLQ (`<topic>.dlq`) | `core/messaging/topics.py`; создаёт backend при старте, хранение бессрочное (`retention.ms=-1`) |
| Конверт: `event_id`, `type`, `schema_version`, `occurred_at`, `producer`, `correlation_id`, `causation_id`, `payload` | `core/messaging/envelope.py` |
| Контракты всех событий и команд | `core/messaging/contracts/<module>.py` |
| Outbox: запись в той же транзакции, что и изменение | `SqlAlchemyOutboxWriter.add(message, key=, correlation_id=, causation_id=)` |
| Relay: публикует по порядку, `FOR UPDATE SKIP LOCKED`, на ошибке останавливает пачку | `core/messaging/relay.py` |
| Inbox: повтор сообщения не обрабатывается дважды | `core/messaging/inbox.py` |

Ключ партиции — `application_id`; для `clients.events` — `organization_id`, `identity.events` — id аккаунта, `support.events` — id обращения, `market.events` — дата, с которой действует ставка. Ответ на команду несёт `causation_id = event_id` команды.

**Подписка.** Модуль возвращает из `subscribers()` список `Subscription(module, topic, group_id, handler, message_types=None)`. Обработчик получает разобранный контракт и `HandlerContext` (`session`, `outbox`, `envelope`, `facade()`, `clock`) и **не коммитит**: изменения обработчика, исходящие сообщения и отметка в inbox коммитятся вместе. Битое сообщение (не JSON, неизвестный тип, невалидный payload) сразу уходит в DLQ; исключение в обработчике — три попытки (паузы 0,5 и 1 с между ними), затем DLQ. `group_id` — `<module>.<назначение>`, уникален.

**Режимы** (`MESSAGING_MODE`):

| Режим | Где | Как |
|---|---|---|
| `kafka` | docker compose | настоящий брокер, relay в фоне |
| `in_process` | локальный запуск без Kafka | те же подписки, доставка в процессе фоновым циклом |
| `manual` | тесты | ничего не работает само; `await app.state.messaging.drain()` доставляет всё до конца |

## Доступ

Пермишны всех модулей — `core/access/permissions.py`. Политика `org_member`: клиент видит строки компаний, где он участник. Модель наследует `OrganizationOwnedMixin`, репозиторий вызывает `apply_access_context`, а `get_access_context_for` сам получает список компаний через `MemberOrganizationsResolver` (реализует clients) — только если у пермишна есть эта политика и пользователь не admin.

## Ядро

`core.domain`: `Money` (Decimal, копейки, без float), `Clock` / `SystemClock` / `FrozenClock`, `DomainEvent`. `core.uow.SqlAlchemyUnitOfWork` — граница транзакции use case. `core.types.SafeString` — строка без HTML. Ошибки: `ValidationError` (422), `InvalidStatusTransitionError` (409), `InfrastructureError` (503), у всех есть `details`. Каждый ответ несёт `X-Request-ID` (тот же id в логах). `GET /ready` проверяет БД и Kafka.

## Тесты

- `tests/fakes/` — фейк каждого фасада (`install(app, ClientsFacade, fake)`), `FakeOutboxWriter`, `FakeInboxGuard`, `FakeUnitOfWork`; `builders.py` — валидные DTO на демо-данных.
- `tests/helpers.py` — `token_for(app, permissions, policies)`, `wait_for`, `create_schema`.
- `tests/test_fakes.py` сверяет сигнатуры фейков с протоколами: изменил фасад — поправь фейк.
- Маркеры: `integration` (testcontainers: Kafka, Postgres) и `e2e` не запускаются по умолчанию, в CI — отдельной задачей `pytest -m integration`.

## Фоновые задачи

Запускаются при старте backend, если `RUN_BACKGROUND_JOBS` включён (в коде по умолчанию включён; тесты его выключают и вызывают задачи напрямую). Каждая останавливается вместе с приложением.

| Задача | Модуль | Что делает | Интервал |
|---|---|---|---|
| `run_offer_expiry` | `applications` | переводит просроченные предложения в `EXPIRED` | 60 с (`APPLICATIONS_OFFER_EXPIRY_INTERVAL_SECONDS`) |
| `run_timeouts` | `process` | шаг без ответа дольше своего таймаута уходит андеррайтеру | 30 с |
| announce | `market` | объявляет `KeyRateChanged` по ставкам, заведённым заранее | 1 ч |
| `run_pre_approval_refresh` | `decision` | пересчитывает предодобрение компаний, у которых оно истекает в ближайшие 3 дня (`DECISION_PRE_APPROVAL_REFRESH_DAYS`) | раз в сутки (`DECISION_PRE_APPROVAL_REFRESH_INTERVAL_SECONDS`), первый проход через 60 с после старта |
| warm-up | `assistant` | загружает локальную модель в память (только `ASSISTANT_LLM_PROVIDER=local`) | повтор через 30 с, пока модель не отвечает |

## Миграции и сиды

Файл `migrations/versions/YYYYMMDD_HHMM_<module>_<что>.py`, `revision = "<module>_<NNNN>"` (первая миграция identity — `0001`), голова одна — сейчас `notifications_0002` (CI проверяет это и сверяет модели с миграциями через `alembic check`). Backend при старте контейнера сам выполняет `alembic upgrade head`. Демо-данные — `backend/seed/demo_data.py`; сиды — `backend/seed/{identity,products,clients,notifications,decision}.py` в таком порядке (`backend/seed/run.py`), запускаются при `SEED_DEMO_DATA=true`, идемпотентны.

## CI

`.github/workflows/ci.yml` на pull request в `develop` и `main` (и как часть деплоя по тегу): ruff, import-linter, mypy по модулям `scoring`, `products`, `decision`, `assistant`, `market`, pytest; Alembic на Postgres (upgrade → downgrade → upgrade, одна голова, `alembic check`); интеграционные тесты в контейнерах (Kafka, Postgres, MinIO); ruff и тесты `external-mocks`; юнит-тесты (Vitest), типы и сборка фронтенда; аудит зависимостей на известные уязвимости — `pip-audit` для backend и `external-mocks`, `npm audit --audit-level=high` для фронта (в PR находка валит проверку, в деплое по тегу только предупреждает); подъём всего стенда через `docker compose up --wait` и проверка по HTTP.
