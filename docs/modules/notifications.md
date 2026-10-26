# Notifications: лента событий и персональные новости

Лента в кабинете клиента и бэк-офиса, персональные новости компании, живое обновление через SSE. Код — `backend/src/modules/notifications`, сид новостей — `backend/seed/notifications.py`.

## Зачем

В кейсе есть пункт «покажите, как изменяется новостная лента под клиента, что содержится в новостях» (см. `settings/case.md`, раздел 5, п. 1). Мы трактуем его так:

- **лента событий** — что происходит с заявками и компанией: статусы, этапы рассмотрения, запросы банка, предложение, советы по улучшению условий;
- **персональные новости** — статьи, подобранные под отрасль (ОКВЭД), продукты и форму бизнеса компании. У ООО «Ромашка» (56.10, общепит) и ИП Иванова (62.01, разработка ПО) разные новости, и у каждой видно, почему она выбрана.

Обе части строятся из данных клиента, поэтому лента «меняется под клиента».

## Структура

Раскладка по слоям из [settings/04-module-structure.md](../../settings/04-module-structure.md).

```
notifications/
├── facade.py                 # NotificationsFacade + реэкспорт DTO и FeedItemType;
│                             # реализация — infrastructure/adapters/notifications_facade.py
├── module.py                 # register: роутеры; wire: фасад; subscribers: пять подписок
├── domain/
│   ├── feed.py               # Recipient, FeedEntry, Delivery, FeedRecord, ключи групп
│   ├── viewers.py            # кто банк, чьи записи читает зритель, StreamGrant
│   ├── templates.py          # тексты ленты с HTML-экранированием подстановок
│   ├── advice.py             # советы из флагов скоринга и кодов решения
│   ├── news.py               # ранжирование новостей под профиль компании
│   └── enums.py              # FeedItemType, Audience, Priority, RecipientType, StreamEventName
├── application/
│   ├── dto/                  # feed (FeedItemDTO, FeedRecordDTO, FeedFilter), news, stream
│   ├── interfaces/           # repositories: FeedStore, NewsStore, TicketStore;
│   │                         # neighbours: Neighbours (чтение соседей), FacadeLookup;
│   │                         # access: OrganizationAccess (видна ли компания, компании участника)
│   ├── deliveries/           # правила «событие → записи»: по файлу на топик-источник
│   │                         # (applications, process, decision, clients, support) + общий context
│   ├── mappers/feed.py       # запись домена → DTO
│   └── use_cases/            # project_event: ProjectEventUseCase (проекция в ленту);
│                             # feed, news, stream, organizations: HTTP;
│                             # account_feed + news: чтение для фасада
├── infrastructure/
│   ├── adapters/             # notifications_facade, neighbours (фасады соседей с деградацией),
│   │                         # organization_access (ClientsFacade.ensure_can,
│   │                         # get_member_organization_ids), session_facades
│   ├── database/             # models: четыре таблицы notifications_*
│   └── repositories/         # feed, news, tickets + mappers (строка таблицы → запись домена)
└── presentation/
    ├── api/                  # /feed (лента, SSE), /news
    ├── schemas/              # feed, news
    ├── consumers.py          # пять подписок → ProjectEventUseCase
    └── dependencies.py       # сборка use case'ов и фасада
```

**Транзакции.** Проекция событий пишет в транзакции Kafka-обработчика и сама не коммитит: записи ленты коммитит ядро вместе с инбоксом. Отметки о прочтении и тикеты SSE коммитятся через `UnitOfWork` в use case'е. Каждый опрос SSE-потока открывает свою короткую сессию.

## Источники событий

Консьюмер подписан на пять топиков, по одной подписке на топик (у платформы `group_id` уникален на подписку): `notifications.feed.applications`, `notifications.feed.process`, `notifications.feed.decision`, `notifications.feed.clients`, `notifications.feed.support`. Фильтр `message_types` — только события ниже, остальные пропускаются.

| Событие | Кому | Тип записи | Приоритет | Нужно действие |
|---|---|---|---|---|
| `ApplicationSubmitted` | участники компании | `status_changed` «Заявка № … отправлена в банк» | normal | — |
| `ApplicationSubmitted` | `role:underwriter` | `status_changed` «Новая заявка № …» | low | — |
| `ApplicationStatusChanged` → `in_review` | участники | `status_changed` (после запроса — «Данные получены») | normal | — |
| → `info_requested` | участники | `info_requested`: комментарий банка и список документов из карточки | high | ✓ |
| → `offer_ready` | участники | `offer_ready`: сумма, срок, ставка, платёж, срок действия | high | ✓ |
| → `signing` | участники | `status_changed` «Осталось подписать договор» | high | ✓ |
| → `signed`, `disbursed`, `expired` | участники | `status_changed` | normal | — |
| → `rejected` | участники | `status_changed` с `client_explanation` из карточки | high | — |
| → `offer_declined`, `cancelled` | участники | `status_changed` | low | — |
| → `draft`, `submitted` | — | не пишем (подача — из `ApplicationSubmitted`) | | |
| `ApplicationInfoProvided`, `ApplicationSigned` | `role:underwriter` | `status_changed` | normal | — |
| `OfferAccepted`, `OfferDeclined`, `ApplicationCancelled` | `role:underwriter` | `status_changed` | low | — |
| `StepCompleted` с `client_stage` | участники | `stage_changed` — **одна запись этапа на заявку**, обновляется | low | — |
| `UserTaskCreated` | `role:<candidate_role>` | `task_assigned`, ссылка на задачу | high | ✓ |
| `UserTaskCompleted` | — | у записи задачи снимается «нужно действие» | | |
| `ProcessFailed` | `role:underwriter` | `status_changed` «Процесс остановлен» | high | ✓ |
| `DecisionMade` (auto) | `role:underwriter` | `status_changed` «Автоматическое решение: …» | low | — |
| `DecisionMade` | участники | `advice` — советы из флагов (см. ниже) и `improvement_hints` | normal / low | — |
| `ManualDecisionRejected` | `role:underwriter` | `status_changed`, ссылка на заявку (задача отклонённого решения уже закрыта) | high | ✓ |
| `PreApprovedOffersUpdated` | участники | `advice` — список предодобренных (одна запись на компанию, обновляется); сюда же входят проектные предложения стартапа | normal | — |
| `PreApprovedOffersUpdated` без предложений у компании, не прошедшей сверку | участники, у которых есть запись предодобрения | `advice` «Уточните данные компании» — **заменяет** запись «вам предодобрено»; ссылка на карточку компании | normal | — |
| `OrganizationVerified` | участники | `status_changed` | low | — |
| `OrganizationVerificationMismatch` | участники | `info_requested` со списком расхождений | high | ✓ |
| `MemberAdded`, `MemberRoleChanged` | сам участник | `status_changed`, ссылка на карточку компании | normal | — |
| `MemberRemoved` | сам (уже бывший) участник | `status_changed` «Доступ к компании … закрыт» — без `organization_id` и без ссылки: открыть компанию он уже не может | normal | — |
| `FinancialReportSubmitted` | участники | `status_changed` | low | — |
| `SupportTicketOpened` | `role:underwriter` | `support` «Новое обращение ТП-…», ссылка `/backoffice/support/{ticket_id}` | normal | ✓ до взятия или закрытия клиентом |
| `SupportMessagePosted` от сотрудника | автор обращения | `support` «Ответ по обращению …» с началом ответа, ссылка `/support/{ticket_id}` — **одна запись на обращение**, обновляется | normal | — |
| `SupportMessagePosted` от клиента во взятое обращение | взявший сотрудник (`account`) | `support` «Клиент написал в обращение …» — одна запись на обращение | normal | — |
| `SupportTicketStatusChanged` сотрудником → `in_progress`, `resolved`, `closed` | автор обращения | `support` — та же запись клиента, что и ответ | normal | — |
| `SupportTicketStatusChanged` → `open` (вернули в очередь) | `role:underwriter` | `support` «Обращение … вернулось в очередь» | normal | ✓ |

`ProcessStarted`, `ProcessCompleted`, `ScoreCalculated` в ленту не попадают: клиент узнаёт итог из статуса заявки.

Записи типа `support` не повторяют переписку: у клиента одна запись на обращение (группа `support:{ticket_id}`), её заменяет последнее событие. Что клиент сделал сам (закрыл, написал в решённое), ему не пишется. У записи очереди (`support-queue:{ticket_id}`) «нужно действие» снимается, когда обращение уходит из `open`. Полная переписка — в модуле [support](support.md).

Чего нет в событии — номер заявки, названия компании и продукта, условия предложения, комментарий запроса — дочитывается фасадами соседей (`ApplicationsFacade.get_card`, `ClientsFacade.get_snapshot`, `ProductsFacade.get_product`). Если фасад не зарегистрирован или сущности нет, текст деградирует («Новая заявка» без номера, «Клиент» вместо названия), событие не падает. Без `ClientsFacade` участники неизвестны — клиентские записи не пишутся, записи бэк-офиса пишутся.

## Получатели

| `recipient_type` | `recipient_id` | Кто читает |
|---|---|---|
| `account` | id аккаунта | участник компании — все из `ClientsFacade.list_members(organization_id)` получают свою копию записи (своя отметка о прочтении) |
| `role` | `underwriter` | бэк-офис: токен с `backoffice.read` (или `admin`) видит записи роли и свои; отметка о прочтении общая на роль |

Записи бэк-офиса — `audience=bank`, клиентские — `audience=client`.

## Идемпотентность

- Inbox платформы: повтор сообщения не доходит до обработчика; обработчик не коммитит сам — записи ленты, inbox и outbox коммитятся вместе.
- UNIQUE `(source_event_id, recipient_type, recipient_id)` в `notifications_feed_items`: даже без inbox повтор события не создаёт дублей. Если одно событие даёт получателю несколько записей (советы), ключ второй и следующих — `uuid5(event_id, "advice:<код>")`.
- Записи с `group_key` (`stage:<application_id>`, `task:<task_id>`, `pre-approved:<organization_id>`) заменяют друг друга: новый этап обновляет запись этапа, а не добавляет новую, и снова делает её непрочитанной.
- Снятие предодобрения (decision без `verified` отдаёт пустой список) — «исправляющая» доставка (`only_existing`): заменяет запись группы `pre-approved:<organization_id>` только у того, у кого она есть; нет записи или в ней уже этот текст — ничего не пишется. Причину берём у `ClientsFacade.get_snapshot`: статус сверки не `verified` — совет «уточните данные компании»; `verified` или компании нет — предложений просто нет, прежняя запись остаётся как есть. Если среди предложений есть проектное (`basis = project`, стартап), список не пуст и запись обновляется как обычно.

## Позиция в потоке (`seq`)

У каждой записи есть `seq` — позиция в потоке и id SSE-события. Новая и обновлённая запись получают `max(seq) + 1`. Два обработчика, взявшие одно значение, сталкиваются на UNIQUE `seq`, проигравший повторяется (три попытки платформы). Поэтому видимые позиции идут по порядку коммита — курсору SSE не грозит пропуск записи из «опоздавшей» транзакции.

## Персональные советы

Сигналы — флаги скоринга (`ScoringFacade.get_result(...).flags`) и коды причин решения (`DecisionFacade.get_decision(...).reason_codes`). Совпадение — по ключевым словам без учёта регистра, поэтому `cash_gap`, `cash_gap_forecast` и `CASH_GAP_RISK` дают один совет; неизвестные флаги игнорируются.

| Совет | Ключевые слова | Ссылка | Не показываем, если заявка на |
|---|---|---|---|
| «Прогнозируется кассовый разрыв — посмотрите кредитную линию» | `cash_gap`, `liquidity_gap` | `/products/CREDIT_LINE` | CREDIT_LINE, OVERDRAFT |
| «Подтвердите выручку выпиской — условия станут лучше» | `revenue_unconfirmed`, `revenue_not_confirmed`, `unverified_revenue`, `revenue_mismatch` … | заявка | — |
| «Бизнесу меньше года — какие продукты доступны» | `young_business`, `business_age`, `short_history` | `/products/OVERDRAFT` | — |
| «Высокая долговая нагрузка — рефинансирование снизит платёж» | `debt_load`, `debt_burden`, `high_dti`, `dsti` | `/products/REFINANCE` | REFINANCE |
| «Есть задолженность перед бюджетом» | `tax_arrear`, `tax_debt` | заявка | — |
| «Сведения о компании расходятся с реестром» | `registry_mismatch`, `verification_mismatch` | карточка компании | — |
| «Залог снизит ставку» | `collateral_recommended`, `ltv_high`, `amount_over_limit` | `/products/SECURED` | SECURED, MORTGAGE, AUTO |

`improvement_hints` из `DecisionMade` — отдельной записью «Как улучшить условия» (список).

## Новости и ранжирование

17 статей в сиде (`seed/notifications.py`, идемпотентно по `slug`, id = `uuid5(slug)`, при повторе обновляются текст и теги, дата публикации сохраняется). Теги: префиксы ОКВЭД, коды продуктов (`seed.demo_data.PRODUCT_CODES`), формы бизнеса, `general`.

Профиль компании: `ClientsFacade.get_snapshot` (ОКВЭД, доп. ОКВЭД, форма), интерес к продуктам — продукты заявок компании (`ApplicationsFacade.list_for_organization`, «есть заявка») и предодобренные (`DecisionFacade.get_pre_approved`, «предодобрен»).

| Совпадение | Баллы | Причина в `relevance` |
|---|---|---|
| основной ОКВЭД по классу (`56` → `56.10`) | 30 | «ОКВЭД 56 — общепит» |
| основной ОКВЭД точнее класса (`56.10`) | 40 | «ОКВЭД 56.10 — общепит» |
| дополнительный ОКВЭД | 15 | «доп. ОКВЭД 62 — разработка ПО» |
| продукт, за каждый | 20 | «продукт OVERDRAFT — предодобрен» |
| форма бизнеса | 10 | «форма бизнеса — ИП» |
| общая статья | 1 | «для всех клиентов» (если других причин нет) |

Статья с тегами, которые не совпали ни по одному признаку, не показывается; общая показывается всем. Порядок: баллы ↓, дата публикации ↓, `slug` — детерминированно. Без компании (или если она неизвестна) — только общие.

Топ-5 на демо-данных:

| ООО «Ромашка» (56.10, ООО) | ИП Иванов (62.01, ИП) |
|---|---|
| Обновить кухню ресторана (ОКВЭД 56.10) | Господдержка для IT-компаний (ОКВЭД 62) |
| Кредит с господдержкой для кафе (ОКВЭД 56) | Оплата по актам: овердрафт (ОКВЭД 62) |
| Как кафе пережить низкий сезон (ОКВЭД 56) | ИП на упрощёнке: подтвердить доход (ИП) |
| ООО и АО: сведения о руководителе (ООО) | Налоговый календарь ИП (ИП) |
| Бизнес-ипотека (ООО) | Ключевая ставка (для всех) |

## SSE

EventSource не умеет слать заголовок `Authorization`, поэтому токен меняется на одноразовый тикет.

1. `POST /feed/stream-ticket` (токен, `feed.read`) → `{ticket, expires_at, expires_in: 30, stream_url}`. Тикет хранится в `notifications_stream_tickets` как sha256 (не в памяти: поток может попасть на другой инстанс backend), вместе с ролями, ленту которых нужно отдавать.
2. `GET /feed/stream?ticket=…[&last_event_id=N]` — тикет гасится условным UPDATE при подключении; неизвестный, использованный или просроченный → 401.
3. События:

| `event` | `id` | `data` |
|---|---|---|
| `feed_item` | `seq` записи | запись как в `GET /feed` |
| `application_updated` | тот же `seq` | `{application_id, organization_id, item_id, type}` — после записи о заявке (статус, этап, запрос, предложение): обновить карточку |
| `heartbeat` | — | `{at}` — если 15 с ничего не было |

4. Доставка — опрос БД раз в секунду (`seq > курсор`, пачками по 50), каждый опрос в своей короткой сессии; in-memory шины нет, поэтому работает при нескольких инстансах.
5. Без `last_event_id` поток начинается «с сейчас». Переподключение: новый тикет и `last_event_id` = последний полученный `id` (или заголовок `Last-Event-ID`); `seq` есть и у записей `GET /feed`, чтобы продолжить поток ровно после загруженной страницы.
6. Поток закрывается через 10 минут — клиент берёт новый тикет (токен за это время мог истечь).

Интервалы и TTL — константы `src/modules/notifications/application/use_cases/stream.py`.

## API

Все ручки — пермишн `feed.read`. Клиент фильтрует только по своим компаниям: `ClientsFacade.ensure_can(account, organization, "view")`, чужая компания → 404. Бэк-офис (`backoffice.read`/`admin`) фильтрует по любой.

Копия записи раскладывается участникам в момент события, поэтому у бывшего участника остаются записи компании. Клиенту лента (`GET /feed`, `unread-count`, `read-all`, `POST /feed/{id}/read`) отдаёт только записи без компании и записи компаний, где он участник сейчас (`ClientsFacade.get_member_organization_ids`). Исключение — записи `support`: обращение принадлежит автору (`own_only`), а не компании. Если участника вернут в компанию, её записи снова станут видны. Бэк-офис читает ленту без этого ограничения.

| Ручка | Что |
|---|---|
| `GET /feed?organization_id=&application_id=&unread_only=&limit=&offset=` | `{items, total, limit, offset}`, новые и обновлённые сверху (по `seq`) |
| `GET /feed/unread-count?organization_id=&application_id=` | `{count}` |
| `POST /feed/{id}/read` | отмечает запись, повтор сохраняет первую отметку; чужая запись или запись компании, из которой клиент вышел, → 404 |
| `POST /feed/read-all?organization_id=&application_id=` | `{updated}` |
| `GET /news?organization_id=&limit=5` | персональные новости `{id, title, body, published_at, relevance[], read}` |
| `POST /news/{id}/read` | 204; неизвестная новость → 404 |
| `POST /feed/stream-ticket`, `GET /feed/stream` | SSE, см. выше |

`title` и `body` — текст с HTML-экранированием: шаблоны — доверенный текст, каждая подстановка (названия, комментарии банка, подсказки) проходит `html.escape`. Отрисовывать можно как HTML.

## Фасад

`NotificationsFacade` (`src/modules/notifications/facade.py`, реализация — `infrastructure/adapters/notifications_facade.py`, регистрирует `module.wire`):

- `unread_count(account_id, organization_id?)`, `latest(account_id, organization_id?, application_id?, limit)` — записи аккаунта; если `IdentityFacade` говорит, что роль аккаунта `underwriter`/`admin`, — и записи бэк-офиса. Прав внутри нет: доступ к компании проверяет вызывающий (BFF).
- `personal_news(organization_id, limit)` — как `GET /news`.

## Таблицы

| Таблица | Что |
|---|---|
| `notifications_feed_items` | записи ленты: получатель, тип, аудитория, текст, ссылка, приоритет, `seq`, `group_key`, `read_at`; UNIQUE `(source_event_id, recipient_type, recipient_id)`, UNIQUE `seq` |
| `notifications_news_items` | новости с тегами (`okved_prefixes`, `product_codes`, `legal_forms` — JSONB, `is_general`) |
| `notifications_news_reads` | `(news_id, account_id)` — прочитанные новости |
| `notifications_stream_tickets` | одноразовые тикеты SSE (sha256, роли, срок, `used_at`); старше часа удаляются при выдаче нового |

Миграции — `migrations/versions/20261022_1200_notifications_feed.py` (`notifications_0001`, после `products_0001`) и `20261114_1000_notifications_member_removed.py` (`notifications_0002`, после `process_0003`, только данные): у уже записанных «Доступ к компании закрыт» (`MemberRemoved`) снимает `organization_id` и ссылку, как теперь пишет код.

## Упрощения

- Записи бэк-офиса адресованы роли, а не конкретному андеррайтеру: отметка о прочтении общая. Роль, отличная от `underwriter` (`candidate_role` задачи), пока никому не показывается.
- Удалённый из компании участник продолжает видеть свои старые записи (их получатель — его аккаунт); новые записи компании ему не приходят.
- Флаги скоринга и коды причин решения сопоставляются по ключевым словам: точные имена флагов задаёт scoring.
- Новости — синтетические статьи сида, без админки; тексты не ссылаются на реальные продукты банков.
- SSE — опрос БД с интервалом 1 с, а не push: проще и переживает несколько инстансов; для демо задержки достаточно.
- Email, SMS и push не отправляются: сценарий целиком внутри кабинета (ограничение кейса).
