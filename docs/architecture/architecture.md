# Архитектура

Источник — схема команды в draw.io, копия в репозитории: [architecture.drawio](architecture.drawio). Открыть: app.diagrams.net → File → Open from → Device или расширение Draw.io Integration в VS Code.

**Правило: меняем схему — правим и `.drawio`, и этот `.md`**, иначе они разъедутся. Ниже — то же, что на схеме, в mermaid и со ссылками на код; где код отличается от схемы, это сказано в конце каждого раздела.

На схеме шесть частей:

| Часть схемы | Раздел | Подробно |
|---|---|---|
| Путь клиента (BPMN, дорожки «Клиент» и «Бэк») | [Путь клиента](#путь-клиента) | [`docs/api/client-journey.md`](../api/client-journey.md) — шаг схемы → ручки |
| Стоп-факторы, «Скоринг система»: модель оценки PD и стратегия решения | [Модель принятия решения](#модель-принятия-решения) | [`scoring.md`](../modules/scoring.md), [`decision.md`](../modules/decision.md) |
| DDD: модули, хранилища, внешние источники | [Модули](#модули) | [`docs/platform.md`](../platform.md), документы модулей |
| Projector и что он отдаёт экранам | [Модели чтения](#модели-чтения) | [`projector.md`](../modules/projector.md) |
| Путь заявки через модули и Kafka | [Путь заявки через Kafka](#путь-заявки-через-kafka) | [`docs/platform.md`](../platform.md), «Kafka» |
| Диаграмма статусов заявки | — | [`docs/state-machine.md`](../state-machine.md) |

## Развёртывание

Модульный монолит: один процесс backend (FastAPI), внутри — 11 модулей. Всё поднимается одним `docker compose up`.

```mermaid
flowchart LR
    Browser["Браузер: сайт клиента и рабочее место сотрудника"] --> Nginx["nginx"]
    Nginx --> Frontend["frontend<br/>Vue 3, статика"]
    Nginx --> Backend["backend (FastAPI)<br/>11 модулей + core"]
    Backend --> Postgres[("Postgres 16<br/>таблицы модулей,<br/>outbox, inbox")]
    Backend <-->|outbox → топики,<br/>консьюмеры с inbox, DLQ| Kafka[("Kafka 3.8, KRaft")]
    Backend -->|S3 API, presigned URL| MinIO[("MinIO<br/>документы заявок")]
    Backend -->|HTTP-адаптеры| Mocks["external-mocks (FastAPI)<br/>ЕГРЮЛ/ЕГРИП, ФНС, БКИ,<br/>ГИР БО, Контур, ЭДО, АБС"]
```

Сервисы, лимиты памяти и проверки здоровья — в [`docs/sla.md`](../sla.md).

## Путь клиента

Дорожка «Клиент» — что видит предприниматель, дорожка «Бэк» — что в это время делает банк.

```mermaid
flowchart TD
    Site["Клиент на сайте"] --> Calc["Кредитный калькулятор"]
    Calc --> Auth{"Авторизован?"}
    Auth -->|нет| Login["Вход в ЛК"] --> Terms
    Auth -->|да| Terms["Клиент выбирает условия"]
    Terms --> Consent["Согласие: БКИ физлица + ПДн"]
    Consent --> Business{"Есть ли бизнес?"}

    Business -->|да, есть обороты| BankData["Данные из базы банка"]
    BankData --> Egrul["Сверка с ЕГРЮЛ"]
    Egrul -->|данные изменились| Reload["Загрузили новые"] --> Egrul
    Egrul --> Prescoring["Предскоринг"]
    Prescoring --> PreApproved["Предодобренное предложение"]
    PreApproved --> Chosen["Клиент выбрал конкретные условия"]
    Chosen --> Requests["Запросы: ГИР БО, Контур, ФНС,<br/>БКИ компании, БКИ руководителя"]
    Requests --> Stop{"Стоп-фактор?"}
    Stop -->|да| Rejected["Отказано"]
    Stop -->|нет| Scoring["Скоринг система:<br/>модель PD → стратегия решения"]
    Scoring --> Sign["Подпиши договор"] --> Done["Кредит оформлен"]

    Business -->|нет, стартап| StartupTerms["Выбрать условия и оформить (стартап)"]
    StartupTerms --> Prescreen["Личный скоринг учредителя (предскрин)"]
    Prescreen --> Passed{"Прошёл предскрин?"}
    Passed -->|нет| StartupRejected["Отказ (стартап)"]
    Passed -->|да| Plan["Загрузить бизнес-план и финмодель"]
    Plan --> Project["Проектная оценка:<br/>бизнес-план, обеспечение, господдержка"]
    Project --> PreApproved
```

| Шаг | Кто в коде |
|---|---|
| Калькулятор с учётом предскоринга | `bff` (`POST /bff/products/{code}/calculate`), расчёт — `products`, предодобрение — `decision` |
| Вход | `identity`: по email или телефону, JWT RS256 |
| Согласия | личные (ПДн, БКИ руководителя) — `identity` (`/me/consents`), согласия компании в заявке — `applications` |
| Данные банка, сверка с ЕГРЮЛ | `clients` (сиды — это «база банка»), реестр — `enrichment.lookup_registry` |
| Предскоринг и предодобрение | `decision` (пересчёт по событиям `clients`), грейд — `scoring` |
| Запросы во внешние источники | `enrichment`: семь источников параллельно, частичный результат при сбоях |
| Стоп-факторы, скоринг, решение | `scoring` → `decision`, порядок задаёт BPMN-маршрут в `process` |
| Договор, подпись, выдача | `applications`: договор с `offer_hash`, подпись с повторным паролем, ЭДО и АБС — моки |
| Ветка стартапа | предскрин — `decision` + `scoring` (`prescreen_v1`), маршрут `startup_v1`: проектная оценка — задача андеррайтеру в `process` |

**Код и схема.** Стоп-факторы на схеме стоят до модели, а в коде их проверяет `decision` уже после скоринга: маршрут всегда «обогащение → скоринг → решение», грейд и коды причин нужны и в журнале, и андеррайтеру. Исход тот же: стоп-фактор → отказ. Стартап на схеме выбирает условия до предскрина; в кабинете предскрин проходят кнопкой до заявки, а заявку на `STARTUP` без пройденного предскрина `decision` отклоняет (сценарий S-9).

## Модель принятия решения

Решение принимают два модуля: `scoring` оценивает риск, `decision` по нему и по правилам банка выбирает исход, сумму, срок и ставку. На каждой заявке scoring считает две независимые оценки на одной шкале A–J: экспертную PD-модель (как на схеме) и обученную ML-модель. Действующие версии — `pd_model_v2`, `ml_logreg_v1` и политика `policy_v5`.

```mermaid
flowchart TD
    Call["Вызов моделей: команда CalculateScore"]

    subgraph PD["Модель оценки PD — scoring, pd_model_v2"]
        Segment{"Сегмент"}
        Segment -->|ЮЛ, обороты в банке ≥ 6 мес.| CardLE["Скоркарта ЮЛ"]
        Segment -->|ИП, обороты в банке ≥ 6 мес.| CardIE["Скоркарта ИП"]
        Segment -->|новый клиент| CardNew["Упрощённая скоркарта"]
        CardLE & CardIE & CardNew --> Features["Признаки на дату заявки"]
        Features --> Full{"Данные полные?"}
        Full -->|нет| Degraded["quality = degraded:<br/>внешняя система не ответила"]
        Full -->|да| Clean["Пропуски и выбросы:<br/>бин «нет данных», винзоризация"]
        Clean --> WoE["Биннинг и WoE"] --> Score["Балл по скоркарте"]
        Score --> Calibrate["Калибровка: балл → PD на 12 мес."]
        Calibrate --> Grade["Грейд A–J по диапазонам PD"]
        Grade --> Reasons["Коды причин: топ-3 признака"]
        Reasons --> LogPD["Журнал: вход, выход, версия модели"]
    end

    subgraph ML["ML-модель — scoring, ml_logreg_v1"]
        MLFeatures["10 признаков из тех же данных"] --> MLWoE["Корзины и WoE"]
        MLWoE --> Logit["Логистическая регрессия: PD на 12 мес."]
        Logit --> MLGrade["Грейд A–J на тех же границах PD"]
        MLGrade --> MLReasons["Коды причин"]
    end

    subgraph Strategy["Стратегия решения — decision, policy_v5"]
        Result["Две оценки: PD, грейд, причины"] --> StopF{"Стоп-фактор?"}
        StopF -->|да| Reject["REJECT"]
        StopF -->|нет| Revenue{"Выручка не подтверждена,<br/>дозапроса ещё не было?"}
        Revenue -->|да| Info["REQUEST_INFO: выписка"]
        Revenue -->|нет| Zones{"Зона PD-модели × зона ML-модели<br/>green A–D · yellow E–G · red H–J"}
        Zones -->|обе red, данные полные| Reject
        Zones -->|"спорная: одна red, нет оценки ML,<br/>сбой источников, расхождения в данных"| Dispute["MANUAL_REVIEW, вид dispute"]
        Zones -->|"проверка: есть yellow, мягкий триггер,<br/>сумма выше автоматики продукта"| Check["MANUAL_REVIEW, вид check"]
        Zones -->|обе green| Limit["Лимит: минимум из ограничений"]
        Limit --> Min{"Лимит ≥ минимума продукта?"}
        Min -->|нет| Reject
        Min -->|да| Term["Срок и платёж: сначала удлинить срок,<br/>потом снизить сумму"]
        Term --> Rate["Ставка: фондирование + PD × LGD<br/>+ капитал + маржа"]
        Rate --> Fits{"Запрос ≤ лимита?"}
        Fits -->|да| Approve["APPROVE на условиях клиента"]
        Fits -->|нет| Counter["COUNTER_OFFER:<br/>макс. сумма, новый платёж"]
        Approve & Counter --> Guarantee["Обеспечение: поручительство<br/>для F–G и крупных сумм"]
        Guarantee --> LogDecision["Журнал: решение, причины, версия политики"]
    end

    Call --> Segment
    Call --> MLFeatures
    LogPD --> Result
    Degraded --> Result
    MLReasons --> Result
```

Пороги и коэффициенты лежат в YAML: `scoring/infrastructure/config/pd_model_v2.yaml`, `ml_logreg_v1.yaml` (его пишет скрипт обучения `backend/ml/train.py`), `decision/infrastructure/config/policy_v5.yaml`. Порядок правил, матрица зон, метрики моделей и разбор S-1…S-9 — в [`scoring.md`](../modules/scoring.md) и [`decision.md`](../modules/decision.md). Андеррайтер видит обе оценки и вид ручной проверки (`check` или `dispute`); клиенту модели не показываются, только общие тексты причин.

**Код и схема.**
- ML-модели на схеме нет. В `policy_v5` она заменяет «Матрицу грейд × сумма»: где модели согласны, решает автоматика, где расходятся или видят умеренный риск — андеррайтер. Матрица грейд × сумма осталась в `policy_v3` и `policy_v4`: вышедшие версии не правятся и нужны для истории и отката.
- Мягкие триггеры на схеме отправляют на ручную проверку сразу. В `policy_v5` они дают «не меньше проверки», но от отказа не спасают, если обе модели в красной зоне.
- Стоп-факторы из таблицы схемы — те, по которым есть данные: ликвидация и банкротство, дисквалификация руководителя, просрочка компании и руководителя, блокировки счетов и недоимка, сообщения о банкротстве, иски и исполнительные производства выше порогов, отрицательный капитал, массовый адрес, запрещённый ОКВЭД. Нет данных — нет правила: реорганизация и исключение из реестра, недостоверность сведений, массовый руководитель, экстремисты, стоп-лист банка и 115-ФЗ. Возраст бизнеса проверяет `products` при подаче.
- Лимит — минимум из семи ограничений, а не шести: к оборотам, выручке, нагрузке, грейду, продукту и группе добавлен LTV для залоговых продуктов.
- «Хранилище признаков» — это снимок обогащения на заявку и сама заявка: признаки строятся из фасадов `enrichment.get_snapshot` и `applications.get_scoring_input`, отдельного feature store нет.
- «Ночной пакет» не сделан: предодобрение пересчитывается по событиям `clients`.

## Модули

```mermaid
flowchart TB
    BFFc["bff: кабинет клиента"]
    BFFb["bff: бэк-офис"]
    subgraph backend["backend — модульный монолит"]
        Identity["identity<br/>Account, Profile, Role,<br/>Auth (JWT), Consent"]
        Clients["clients<br/>Organization, Members,<br/>Financial reports, Verification"]
        Products["products<br/>Credit products, Recommender,<br/>Payment calculator"]
        Applications["applications<br/>CreditApplication, Documents,<br/>Info requests, Offer"]
        Process["process<br/>Workflows (BPMN), Process instances,<br/>User tasks, Step registry"]
        Enrichment["enrichment<br/>Snapshots, адаптеры источников"]
        Scoring["scoring<br/>PD model, ML model, Scorecard,<br/>Scoring results, Prescreen"]
        Decision["decision<br/>Credit policy, Decisions,<br/>Pre-approved offers"]
        Notifications["notifications<br/>Feed, Personal news, SSE"]
        Projector["projector<br/>модели чтения"]
        Core["core (shared kernel)<br/>UoW, outbox relay, inbox, errors,<br/>access (RBAC + ABAC), settings, logging"]
    end
    Kafka[("Kafka")]
    Postgres[("Postgres")]
    MinIO[("MinIO")]
    Mocks["external-mocks"]

    BFFc & BFFb -->|фасады| backend
    BFFc & BFFb -->|read API| Projector
    Applications -->|S3 API| MinIO
    Enrichment -->|HTTP| Mocks
    Applications -->|HTTP: ЭДО, АБС| Mocks
    Clients & Applications & Process & Enrichment & Scoring & Decision -->|outbox| Kafka
    Kafka --> Process & Applications & Enrichment & Scoring & Decision & Clients & Notifications & Projector
    backend --> Postgres
```

| Модуль | Отвечает за | Документ |
|---|---|---|
| `core` | Unit of Work, outbox/relay/inbox, DLQ, ошибки, доступ (пермишны и политики), настройки, `X-Request-ID` в логах | [`platform.md`](../platform.md) |
| `identity` | вход по email или телефону, JWT RS256, роли, профиль, личные согласия | [`identity.md`](../identity.md) |
| `clients` | компании, участники и их права (подаёт, подписывает), доверенности, финотчётность, сверка с ЕГРЮЛ | [`clients.md`](../modules/clients.md) |
| `products` | каталог из 9 продуктов, подбор с причинами, калькулятор, eligibility | [`products.md`](../modules/products.md) |
| `applications` | заявка и её статус (единственный владелец), документы в MinIO, дозапросы, оффер, договор, подпись, выдача | [`state-machine.md`](../state-machine.md) |
| `process` | движок BPMN: маршрут продукта (`express_v1`, `standard_v1`, `secured_v1`, `mortgage_v1`, `startup_v1`), команды модулям, задачи андеррайтера | — |
| `enrichment` | ЕГРЮЛ/ЕГРИП, ФНС, БКИ компании и руководителя, ГИР БО, Контур, прогноз кассового разрыва по выпискам; снимок на заявку | [`enrichment.md`](../modules/enrichment.md) |
| `scoring` | две оценки риска на шкале A–J: PD-модель на скоркартах и ML-модель (логистическая регрессия), коды причин; предскрин учредителя | [`scoring.md`](../modules/scoring.md) |
| `decision` | кредитная политика: стоп-факторы, триггеры, матрица зон двух моделей, лимит, ставка, исход и объяснение; предодобрение | [`decision.md`](../modules/decision.md) |
| `notifications` | лента событий и персональные новости, SSE | [`notifications.md`](../modules/notifications.md) |
| `projector` | денормализованные таблицы под списки, очередь и метрики | [`projector.md`](../modules/projector.md) |
| `bff` | ответы под экраны кабинета клиента и бэк-офиса | [`client-journey.md`](../api/client-journey.md) |

Модули читают друг друга только через фасады (`facade.py`), а пишут друг другу только командами через Kafka; границы проверяет import-linter. Устройство модуля внутри — [`settings/04-module-structure.md`](../../settings/04-module-structure.md).

**Код и схема.**
- BFF на схеме — отдельный сервис перед бэкендом; в коде это модуль `bff` того же процесса: он ходит в соседей через фасады, а не по HTTP.
- В Postgres у модулей не отдельные схемы, а свои таблицы с префиксом модуля в одной базе (у identity — `roles`, `accounts`, `profiles`, `identity_consents`).
- В MinIO один бакет документов заявок (`MINIO_BUCKET_NAME`, по умолчанию `credit-documents`); аватаров профиля нет.
- В identity нет сессий: только access-токен без хранения, refresh нет.
- Ошибки — `{code, message, details}` с HTTP-статусом, а не RFC 9457.
- К Kafka на схеме подключены все модули. Публикуют `clients`, `applications`, `process`, `enrichment`, `scoring` и `decision`; топик `identity.events` создаётся, но identity в него пока ничего не пишет; `notifications` и `projector` только читают.

## Модели чтения

Projector строит по событиям таблицы под экраны, чтобы BFF не собирал списки из пяти модулей на каждый запрос.

| Таблица | Что | Откуда |
|---|---|---|
| `projector_application_overview` | «Мои заявки»: номер, продукт, сумма, статус, этап, нужно ли действие клиента | applications, process, decision |
| `projector_underwriting_queue` | очередь андеррайтера: компания, сумма, грейд, причины ручной проверки, SLA, исполнитель | process, scoring, decision, applications |
| `projector_application_timeline` | этапы заявки со временем, клиенту — только клиентские | process, applications |
| `projector_organization_dashboard` | дашборд компании: активные заявки, предодобренный лимит, «что сделать» | clients, decision, applications |
| `projector_backoffice_metrics` | воронка статусов, доля автоодобрений, время до решения | все события |

Карточку одной заявки BFF читает из `applications` напрямую: проекции — только для списков и дашбордов. Перестроить таблицы с нуля можно из Kafka (хранение бессрочное) — `scripts/projector_rebuild.py`.

## Путь заявки через Kafka

Успешный сценарий «подача → решение → выдача», как на схеме. Обработчики пишут изменения и исходящие сообщения в одной транзакции (outbox), ключ партиции — `application_id`, ответ на команду несёт `causation_id` = `event_id` команды.

```mermaid
sequenceDiagram
    autonumber
    actor C as Клиент (UI → BFF / API)
    participant A as applications
    participant K as Kafka
    participant P as process
    participant E as enrichment
    participant M as external-mocks
    participant S as scoring
    participant D as decision
    participant N as notifications

    C->>A: POST /applications/{id}/submit
    A-->>C: SUBMITTED
    A->>K: ApplicationSubmitted · applications.events
    K->>P: ApplicationSubmitted → старт маршрута по workflow_code продукта
    P->>K: StartReview · applications.commands
    K->>A: StartReview → IN_REVIEW
    Note over P: проверка полноты — фасад applications.get_completeness
    P->>K: FetchEnrichment · enrichment.commands
    K->>E: FetchEnrichment
    E->>M: HTTP: ЕГРЮЛ ‖ ФНС ‖ БКИ ‖ ГИР БО ‖ Контур ‖ БКИ руководителя
    M-->>E: ответы (таймауты, ретраи)
    E->>K: EnrichmentCompleted · enrichment.events
    K->>P: EnrichmentCompleted
    P->>K: CalculateScore · scoring.commands
    K->>S: CalculateScore (фасады applications.get_scoring_input, enrichment.get_snapshot)
    S->>K: ScoreCalculated · scoring.events
    K->>P: ScoreCalculated
    P->>K: MakeDecision · decision.commands
    K->>D: MakeDecision: стоп-факторы → лимит → ставка → маршрутизация
    D->>K: DecisionMade(APPROVE) · decision.events
    K->>P: DecisionMade → шлюз по outcome
    P->>K: PresentOffer · applications.commands
    K->>A: PresentOffer → OFFER_READY
    A->>K: ApplicationStatusChanged · applications.events
    K->>N: ApplicationStatusChanged
    N-->>C: SSE: «Решение готово»
    C->>A: POST /applications/{id}/offer/accept → SIGNING
    A->>K: OfferAccepted
    K->>P: OfferAccepted
    C->>A: POST /applications/{id}/sign {password, offer_hash} → SIGNED
    A->>K: ApplicationSigned
    K->>P: ApplicationSigned
    P->>K: MarkDisbursed · applications.commands
    K->>A: MarkDisbursed → DISBURSED (выдача через АБС-мок)
    P->>K: ProcessCompleted · process.events
    K->>N: ProcessCompleted
    N-->>C: SSE: «Деньги отправлены»
```

Ручное рассмотрение, дозапрос и отказ идут по тем же топикам: `decision` отвечает `MANUAL_REVIEW` → `process` ставит задачу андеррайтеру (`UserTaskCreated`) → решение андеррайтера уходит командой `RecordManualDecision`; `REQUEST_INFO` → `RequestInfo` → клиент отвечает (`ApplicationInfoProvided`) → маршрут продолжается; `REJECT` → `RejectApplication`.

| Топик | Публикует | Читают |
|---|---|---|
| `applications.events` | applications | process, notifications, projector |
| `applications.commands` | process | applications |
| `process.events` | process | applications (этап для клиента), notifications, projector |
| `enrichment.commands` / `enrichment.events` | process / enrichment | enrichment / process, clients |
| `scoring.commands` / `scoring.events` | process / scoring | scoring / process |
| `decision.commands` / `decision.events` | process / decision | decision / process, notifications, projector |
| `clients.events` | clients | decision (предодобрение), notifications, projector |
| `identity.events` | — (создаётся на будущее) | — |

У каждого топика есть `<topic>.dlq`. Контракты — `backend/src/core/messaging/contracts/`.

**Код и схема.** Подача отвечает `200` со статусом `submitted`, а не `202`. Подпись, кроме пароля, несёт `offer_hash` договора: клиент подписывает ровно то, что видел.
