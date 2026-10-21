# Projector — модели чтения

Денормализованные таблицы под экраны: список заявок клиента, дашборд компании, очередь андеррайтера, лента событий заявки, метрики бэк-офиса. Projector сам ничего не решает и своих ручек не имеет: экраны читают его через BFF, который до вызова проверяет права. Код — `backend/src/projector`, контракт — `src/projector/facade.py`.

## Как устроено

```
applications.events ─┐
process.events ──────┤  событие = сигнал   ┌─ ApplicationsFacade.get_card
decision.events ─────┼──► ReadModelProjector ┼─ ProcessFacade.get_task
clients.events ──────┘   .apply()           ├─ ScoringFacade.get_result
                                            ├─ DecisionFacade.get_decision / get_pre_approved
                                            └─ ProductsFacade.get_product, ClientsFacade.get_snapshot
                              │
                              ▼  upsert / пересчёт
              projector_* (5 таблиц) ──► ProjectorFacade ──► BFF
```

| Слой | Что |
|---|---|
| `domain/` | записи моделей чтения и правила: версия карточки, «первое финальное решение», стадия задачи, ячейка метрик, тексты ленты |
| `application/projection.py` | `ReadModelProjector.apply(envelope, message)` — единственный код проекции; его вызывают и живой консьюмер, и rebuild |
| `application/timeline.py` | какое событие становится записью ленты и что в ней видит клиент |
| `infrastructure/` | таблицы, `SqlAlchemyReadModelStore`, `ProjectorFacadeImpl`, подписки (`consumer.py`), прогон rebuild (`rebuild.py`) |

**Подписки.** Ядро разрешает одной consumer group читать один топик, поэтому групп четыре: `projector.read-models.applications`, `.process`, `.decision`, `.clients`. Обработчик у всех один. Инбокс ядра отсекает повтор доставки.

**Событие — сигнал.** Текущее состояние projector дочитывает у модуля-владельца через фасад (в транзакции обработчика) и хранит вместе с версией. Историю (ленту, момент первого решения) берёт из самого события: `occurred_at` и payload. Соседа, чей фасад ещё не подключён (`FacadeNotRegisteredError`), projector пропускает и пишет предупреждение в лог: строки получаются беднее, но проекция не встаёт.

## Таблицы и откуда поля

| Таблица | Ключ | Поля и источник |
|---|---|---|
| `projector_application_overview` | `application_id` | карточка заявки (`get_card`): номер, `organization_id`, продукт, сумма, срок, статус, `client_stage`, оффер (сумма, ставка), `submitted_at`, `updated_at`, `version` → `source_version`; название продукта — `products.get_product`; компания и ИНН — снимок в карточке (у черновика — `clients.get_snapshot`); `action_required` — из статуса (`info_requested` → `info`, `offer_ready` → `offer`, `signing` → `sign`). Из событий `DecisionMade`: `decision_outcome`, `decided_by`, `decided_at` (первое финальное решение), `manual_review_at` (первая отправка андеррайтеру), `time_to_decision_sec`. С `OrganizationOwnedMixin`: политика `org_member` работает и здесь |
| `projector_underwriting_queue` | `task_id` | задача (`process.get_task`): тип, роль, статус, исполнитель, срок, создана; стадия задачи → `source_version`. Из обзора: номер, компания, ИНН, продукт, сумма. Из скоринга (`get_result`): балл, грейд, `cash_gap` (флаг `cash_gap…`). `routing_reasons` — `reason_codes` текущего решения, пока оно `MANUAL_REVIEW` |
| `projector_application_timeline` | `id` = uuid5 от `event_id` | одна запись на событие; `source_event_id` уникален; `at` = `occurred_at`; `kind` (`status`, `stage`, `task`, `decision`), `title`, `audience` (`client` / `bank`), `details` |
| `projector_organization_dashboard` | `organization_id` | счётчики из обзора: активные заявки (`ACTIVE_STATUSES` applications), ждущие клиента (`action_required ≠ none`); предодобренные — `decision.get_pre_approved` (максимум суммы, минимум ставки); `last_activity_at` — самое позднее событие компании |
| `projector_backoffice_metrics` | `(day, product_code)` | на день (UTC) и продукт: `submitted`, `approved`, `counter_offers`, `rejected`, `manual_reviews`, `auto_decisions`, `decision_time_total_sec`, `decision_time_count`; среднее считается при чтении |

Индексы: обзор — `(organization_id, updated_at)`, `(organization_id, status)`, `submitted_at`, `decided_at`, `manual_review_at` (пересчёт метрик); очередь — `(candidate_role, status, …)` под каждую сортировку; лента — `(application_id, at)`.

## События → обновления

Любое событие заявки обновляет обзор (карточка), все задачи заявки в очереди, ячейки метрик, которых касается строка обзора (до и после изменения), и дашборд компании.

| Событие | Дополнительно |
|---|---|
| `ApplicationSubmitted` | — (запись ленты даёт смена статуса) |
| `ApplicationStatusChanged` | лента: `status`, клиенту, заголовок по новому статусу |
| `ApplicationInfoProvided` | лента: `status`, банку («Клиент ответил на запрос сведений») |
| `OfferAccepted`, `OfferDeclined`, `OfferExpired`, `ApplicationSigned`, `ApplicationCancelled` | — (их видно по смене статуса) |
| `ProcessStarted`, `ProcessCompleted`, `ProcessFailed` | лента: `stage`, банку |
| `StepCompleted` | лента: `stage`; с `client_stage` — клиенту (заголовок = этап), без — банку |
| `UserTaskCreated` | строка очереди (если process о задаче не знает — из события, статус `open`); лента: `task`, банку |
| `UserTaskCompleted` | задача закрыта (`done`), уходит из `open`; лента: `task`, банку |
| `DecisionMade` | факты решения в обзоре; лента: `decision`, клиенту — только то, что ему можно (исход, кем принято — автоматически или специалистом, оффер, запрошенные сведения, пояснение, подсказки, альтернатива; без reason codes и балла) |
| `ManualDecisionRejected` | лента: `decision`, банку |
| `PreApprovedOffersUpdated` | дашборд: предодобренные предложения |
| `clients.events` (`MemberAdded`, `FinancialReportSubmitted`, …) | дашборд: `last_activity_at` (строка создаётся, если её не было) |

Клиенту `get_timeline(..., "client")` отдаёт только записи `audience=client`, банку — все.

## Версии и идемпотентность

- **Карточка.** Строка обзора хранит `source_version` = `version` карточки; прочитанная более старая версия ничего не перезаписывает (отстающая реплика, параллельные обработчики разных топиков).
- **Задача.** У задачи нет версии, есть стадия: `open` (0) → `in_progress` (1) → `done` / `cancelled` (2). Закрытая задача не «открывается» старым чтением.
- **Решение.** В обзоре — самое раннее финальное решение (`APPROVE`, `COUNTER_OFFER`, `REJECT`) и самый ранний `MANUAL_REVIEW`: повтор и опоздавшее событие дают ту же строку при любом порядке.
- **Лента.** id записи = uuid5 от `event_id`, `source_event_id` уникален: повтор не пишет вторую запись.
- **Метрики.** Ячейку не инкрементируем — пересчитываем из строк обзора, попавших в этот день и продукт. Поэтому повтор, опоздание или rebuild не считают дважды. Пустая ячейка удаляется.
- **Дашборд.** Счётчики пересчитываются из обзора, `last_activity_at` берётся как максимум.

Итог: все таблицы — функция текущего состояния соседей и множества событий, а не их порядка. На этом держатся и повторная доставка, и rebuild (тест `test_rebuild.py`).

## Метрики для SLA

`get_backoffice_metrics(date_from, date_to)` отдаёт строки по дням и продуктам и итог за период:

| Показатель | Как считается |
|---|---|
| `submitted` | заявки, поданные в этот день (`submitted_at` карточки) |
| `decided` | первые финальные решения дня: `approved + counter_offers + rejected` |
| `auto_decision_share` | `auto_decisions / decided` за период (решения `decided_by = auto`); `None`, если решений нет |
| `avg_time_to_decision_sec` | среднее «подача → первое финальное решение», по дню решения; ожидание ответа клиента на запрос сведений входит |
| `manual_reviews` | заявки, отправленные андеррайтеру в этот день (`DecisionMade` с `MANUAL_REVIEW`) |

Пример на сценарии из golden-теста: 4 подачи, 3 решения, доля авторешений 0,6667, среднее время до решения 3020 с.

## Rebuild

Перестроить модели чтения с нуля (после изменения проекции или потери данных):

```bash
cd backend
uv run python -m scripts.projector_rebuild
```

Нужны те же `DATABASE_URL` и `KAFKA_BOOTSTRAP_SERVERS`, что у приложения. Скрипт:

1. очищает все пять таблиц projector;
2. читает четыре топика с начала новой consumer group `projector.read-models.rebuild-<UTC-время>` (`auto_offset_reset=earliest`); топики хранятся бессрочно;
3. применяет каждое событие тем же `ReadModelProjector.apply()` в своей транзакции (без инбокса: таблицы пустые, проекция идемпотентна; на ошибке — три попытки);
4. останавливается, дойдя до конечных офсетов, снятых при назначении партиций; дальше события обрабатывает живой консьюмер.

Пишет в те же таблицы. Живой консьюмер можно не останавливать: оба только делают upsert и пересчёт, поэтому сходятся. Пока rebuild не догнал, списки неполные. Код возврата — 1, если хоть одно событие не применилось (детали в логе).

## Фасад

`ProjectorFacadeImpl(session, clock)` регистрирует `module.wire`. Прав внутри нет.

| Метод | Что отдаёт |
|---|---|
| `list_applications(organization_id, status=None, limit, offset)` | заявки компании, новые изменения первыми, `total` — до пагинации |
| `get_organization_dashboard(organization_id)` | дашборд или `None`, если по компании ещё не было событий |
| `get_underwriting_queue(role, status="open", sort, limit, offset)` | задачи роли; `open` — `open` и `in_progress`, `closed` — `done` и `cancelled`, иначе точный статус. Сортировки: `due_at` — ближайший срок первым, `amount` — крупные первыми, `score` — рискованные (низкий балл) первыми, `created_at` — старые первыми; пустые значения в конце. `overdue` считается при чтении по `clock` |
| `get_timeline(application_id, audience)` | записи по времени; клиенту — только клиентские |
| `get_backoffice_metrics(date_from, date_to)` | см. «Метрики для SLA» |

## Упрощения

- Черновик попадает в projector только с первым событием (обычно — подачей); список черновиков BFF берёт у applications (`list_for_organization`).
- Взятие задачи в работу без события (`in_progress`, исполнитель) появится в очереди со следующим событием по заявке.
- `routing_reasons` — коды причин из decision (`reason_codes`), а не текст: подписи — забота BFF/фронта. У закрытой задачи после финального решения список пуст — это функция текущего состояния, иначе rebuild не совпадал бы с живой сборкой.
- Флаг кассового разрыва — любой флаг скоринга, начинающийся с `cash_gap`.
- Дни метрик — по UTC.
- Rebuild пишет в рабочие таблицы, а не во временные с переключением: проще, и сходимость с живым консьюмером проверена тестом.
- Образ backend (`backend/Dockerfile`) пока не копирует `scripts/`: rebuild запускается из `backend/` локально (или нужно добавить `COPY scripts ./scripts`).
