# Документация

Карта документов репозитория. Запуск стенда, демо-учётки и сценарий проверки — в корневом
[README](../README.md).

## С чего начать

| Кто вы | Что читать по порядку |
|---|---|
| Эксперт, 15 минут | [README](../README.md) → [что умеет кабинет](product/features.md) → [архитектура](architecture/architecture.drawio) → [скоринг и решение](scoring-architecture.md) |
| Проверяю API руками | [описание API и коллекция Yaak](api/README.md) → [путь клиента по шагам](../settings/client-journey.md) → Swagger `http://localhost:8080/api/docs` |
| Разбираюсь в кредитной логике | [скоринг и решение целиком](scoring-architecture.md) → [scoring](modules/scoring.md) → [decision](modules/decision.md) → [BPMN-процесс](process/bpmn.md) → [115-ФЗ](compliance-115.md) |
| Разработчик бэкенда | [платформа](platform.md) → [архитектура](architecture/architecture.drawio) → [структура модуля](../settings/04-module-structure.md) → документ своего модуля → [модель данных](data-model.md) |

## Кейс и продукт

| Документ | Что в нём |
|---|---|
| [settings/case.md](../settings/case.md) | текст кейса, наше понимание, чек-лист сдачи, ответы организаторов |
| [settings/webinar-2026-10-21.md](../settings/webinar-2026-10-21.md) | ответы экспертов на вебинаре: границы задачи, моки, скоринг, ИИ |
| [settings/chat-insights.md](../settings/chat-insights.md) | выводы из чатов хакатона: сроки, правила, опыт прошлых лет |
| [product/features.md](product/features.md) | ключевые фишки, исследование, результаты, скриншоты |
| [product/credit-products.md](product/credit-products.md) | девять видов кредитов, выгодоприобретатель и третьи лица |

## Архитектура и процесс

| Документ | Что в нём |
|---|---|
| [architecture/architecture.drawio](architecture/architecture.drawio) | схема draw.io — единая точка правды по архитектуре: модули, Kafka, путь заявки от подачи до предложения |
| [platform.md](platform.md) | как устроен модуль и фасады, Kafka с outbox/inbox/DLQ, доступ, ядро, тесты, миграции и сиды, CI |
| [scoring-architecture.md](scoring-architecture.md) | **скоринг и кредитное решение сквозь модули**: обогащение → стоп-факторы → две модели → политика → исход; предодобрение, стартап, версии, аудит |
| [process/bpmn.md](process/bpmn.md) | процесс одобрения в BPMN, пять маршрутов, шаги и таймауты, сравнение со схемой «как сейчас», нормы |
| [state-machine.md](state-machine.md) | статусы заявки и переходы |
| [data-model.md](data-model.md) | модель данных по модулям (ER) |
| [sla.md](sla.md) | SLA, отказоустойчивость, деградация |

## Модули бэкенда

| Модуль | Документ |
|---|---|
| `identity` — вход, JWT, RBAC + ABAC, согласия | [identity.md](identity.md) |
| `clients` — компании, участники, доверенности, сверка с ЕГРЮЛ, отчётность | [modules/clients.md](modules/clients.md) |
| `market` — ключевая ставка | [modules/market.md](modules/market.md) |
| `products` — каталог, подбор, калькулятор, eligibility | [modules/products.md](modules/products.md) |
| `applications` — заявка, документы, предложение, договор | [modules/applications.md](modules/applications.md) |
| `process` — движок BPMN, задачи андеррайтера | [modules/process.md](modules/process.md) |
| `enrichment` — внешние источники, прогноз по выписке | [modules/enrichment.md](modules/enrichment.md) |
| `scoring` — PD-модель, ML-модель, предскрин, проектная оценка | [modules/scoring.md](modules/scoring.md) |
| `decision` — кредитная политика, предодобрение, версии | [modules/decision.md](modules/decision.md) |
| `notifications` — лента событий и новости | [modules/notifications.md](modules/notifications.md) |
| `support` — чат с поддержкой | [modules/support.md](modules/support.md) |
| `projector` — модели чтения | [modules/projector.md](modules/projector.md) |
| `bff` — ответы под экраны | [modules/bff.md](modules/bff.md) |
| `assistant` — умный помощник | [ai.md](ai.md), [assistant-api.md](assistant-api.md) |

## API

| Документ | Что в нём |
|---|---|
| [api/README.md](api/README.md) | путеводитель: OpenAPI, Swagger, коллекция Yaak и её структура |
| [api/openapi.json](api/openapi.json) | спецификация OpenAPI, выгружается из приложения |
| [settings/client-journey.md](../settings/client-journey.md) | путь клиента по шагам: какие ручки и что отвечает BFF |
| [api/yaak/](api/yaak/), [api/yaak.json](api/yaak.json) | коллекция Yaak: сценарии S-1…S-10 и справочник ручек |

## Закон и безопасность

| Документ | Что в нём |
|---|---|
| [compliance-115.md](compliance-115.md) | 115-ФЗ на каждой заявке, группа риска, третьи лица, ст. 16 152-ФЗ |
| [personal-data.md](personal-data.md) | персональные данные (152-ФЗ) |
| [contract-signing.md](contract-signing.md) | договор PDF, ПЭП клиента и УНЭП банка, проверка подлинности (63-ФЗ) |

## Рядом с кодом

| Документ | Что в нём |
|---|---|
| [backend/ml/README.md](../backend/ml/README.md) | обучение и валидация ML-модели, отчёты `backend/ml/reports/` |
| [external-mocks/README.md](../external-mocks/README.md) | моки внешних систем: эндпоинты, демо-компании, сбои |
| [e2e/README.md](../e2e/README.md) | E2E-тесты кабинета на Playwright |
| [frontend/README.md](../frontend/README.md) | фронтенд: запуск, структура |
| [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) | сторонние компоненты, модели, смоделированные интеграции |
| [settings/](../settings/) | правила команды: коммиты, ветки, сообщения, структура модуля |
