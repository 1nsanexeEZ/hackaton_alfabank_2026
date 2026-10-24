# Модуль `support`

## Зачем

Чат клиента с техподдержкой банка (#210). Клиент из кабинета задаёт вопрос, и появляется
обращение. Обращение попадает в общую очередь, её видят андеррайтеры и админ. Один из них берёт
обращение, и дальше клиент переписывается с ним. Сотрудник решает или закрывает обращение, может
вернуть его в очередь. Код — `backend/src/modules/support`.

## Структура

Раскладка по слоям из [settings/04-module-structure.md](../../settings/04-module-structure.md).

```
support/
├── module.py                 # register: роутеры; фасада и подписок нет (как у bff)
├── domain/
│   ├── ticket.py             # агрегат SupportTicket: переходы, правила take, записи и закрытия
│   ├── entities.py           # TicketMessage
│   ├── statuses.py           # таблица переходов статусов
│   ├── value_objects.py      # TicketNumber, Staff(account_id, supervisor), clean_text
│   ├── events.py             # TicketOpened, MessagePosted, TicketStatusChanged
│   └── enums.py              # TicketStatus, Side
├── application/
│   ├── dto/tickets.py        # NewTicketDTO, TicketQuery, TicketSummaryDTO, TicketViewDTO, QueueScope
│   ├── interfaces/           # repositories (TicketRepository, TicketChangedError), outbox
│   ├── mappers/              # dto: агрегат → DTO; messages: события → контракты support.events
│   └── use_cases/            # client, staff; common — загрузка под политиками, save + outbox
├── infrastructure/
│   ├── adapters/unit_of_work.py  # StaleDataError / IntegrityError → 409 version_conflict
│   ├── database/models.py    # TicketRecord (OwnableMixin, VersionMixin), MessageRecord
│   └── repositories/         # tickets, mappers
└── presentation/
    ├── api/                  # client (/support/tickets), staff (/support/queue)
    ├── schemas/tickets.py    # тексты — SafeString с лимитами длины
    └── dependencies.py
```

Соседей модуль читает только через фасады: `IdentityFacade` (имена в карточке), `ClientsFacade`
(доступ клиента к компании), `ApplicationsFacade` (заявка, к которой привязан вопрос). Своих
HTTP-исключений нет, ошибки — исключения core с кодом в `details.code`.

## Модель

`SupportTicket`: `number` (`ТП-2026-000001`, sequence `support_ticket_number_seq`), `author_id`
(клиент), `subject`, `status`, необязательные `organization_id` и `application_id`, `assignee_id`,
`taken_at`, `resolved_at`, `closed_at`, `messages[]`, `version`. Сообщение — `side` (`client` /
`staff`), автор, текст, время. Тема — до 200 символов, сообщение — до 4000; пустой текст — 422.

Привязка к компании и заявке необязательна. Чужая компания или чужая заявка — 404. Компания
заявки подставляется сама; явно переданная другая компания — 422.

## Статусы

| Из | В | Кто и как |
|---|---|---|
| `open` | `in_progress` | сотрудник взял (`take`) |
| `open` | `closed` | клиент закрыл |
| `in_progress` | `open` | сотрудник вернул в очередь (`release`), исполнитель снимается |
| `in_progress` | `resolved` | сотрудник решил |
| `in_progress` | `closed` | сотрудник или клиент закрыл |
| `resolved` | `in_progress` | клиент написал — обращение вернулось к тому же сотруднику |
| `resolved` | `closed` | сотрудник или клиент закрыл |

`closed` — финальный: в закрытое обращение не пишет никто (409 `ticket_closed`). Другой переход —
409 `invalid_transition`.

## Правила сотрудника

- **Один исполнитель.** Взять можно только невзятое обращение. Взятое не берёт никто, даже тот,
  кто его держит: 409 `already_taken`, в `details.assignee_id` — кто держит.
- Отвечать, решать, закрывать и возвращать в очередь может только исполнитель. Невзятое —
  409 `not_taken`, взятое другим — 403 `not_assignee`.
- **Админ — супервизор.** Во взятом другим обращении админ может отвечать, решать, закрывать и
  возвращать в очередь, исполнитель при этом не меняется. Открытое обращение админ берёт, как все.
  Так у обращения всегда один исполнитель, а админ может подхватить зависший разговор.

## Take и гонка

Двое жмут «взять» одновременно — взять должен один, второй получает 409 `already_taken`.

- `TicketRecord` с `version_id_col` (как `ApplicationRecord`): запись идёт как
  `UPDATE … WHERE version = :loaded`, опоздавший получает `StaleDataError`.
- `SupportUnitOfWork` после rollback превращает `StaleDataError` и `IntegrityError` в
  `TicketChangedError` (409 `version_conflict`).
- `TakeTicketUseCase` на `TicketChangedError` один раз повторяет попытку на свежих данных. Уже
  взяли — 409 `already_taken`. Было другое изменение (например, клиент написал) — take проходит.
- Вторая линия — UNIQUE `(ticket_id, position)` в `support_messages`: два сообщения не займут одно
  место.

Остальные действия не повторяются: на 409 `version_conflict` клиент перечитывает карточку.
Гонку проверяют `tests/support/test_take_race.py` на двух настоящих сессиях.

## API

Все ручки отвечают карточкой `TicketOut` (поля списка + `author_name`, `assignee_name`,
`messages[]`), списки — массивом `TicketListItem` с `message_count`, `last_message_at`,
`last_message_side`. `last_message_side = "client"` в незакрытом обращении — банк должен ответить.

| Метод | Путь | Права | Что |
|---|---|---|---|
| POST | `/support/tickets` | `support.create` | вопрос с первым сообщением; 201 |
| GET | `/support/tickets?status=&limit=&offset=` | `support.read` | мои обращения, свежие сверху |
| GET | `/support/tickets/{ticket_id}` | `support.read` | обращение с перепиской; чужое — 404 |
| POST | `/support/tickets/{ticket_id}/messages` | `support.create` | написать в своё обращение; 201 |
| POST | `/support/tickets/{ticket_id}/close` | `support.create` | закрыть своё обращение |
| GET | `/support/queue?status=&scope=all\|unassigned\|mine&limit=&offset=` | `support.manage` | очередь |
| GET | `/support/queue/{ticket_id}` | `support.manage` | карточка |
| POST | `/support/queue/{ticket_id}/take` | `support.manage` | взять |
| POST | `/support/queue/{ticket_id}/release` | `support.manage` | вернуть в очередь |
| POST | `/support/queue/{ticket_id}/messages` | `support.manage` | ответить клиенту; 201 |
| POST | `/support/queue/{ticket_id}/resolve` | `support.manage` | решить |
| POST | `/support/queue/{ticket_id}/close` | `support.manage` | закрыть |

## Права

| Пермишн | `client` | `underwriter` |
|---|---|---|
| `support.read` | ✓ `own_only` | — |
| `support.create` | ✓ `own_only` | — |
| `support.manage` | — | ✓ |

`own_only` держится на `owner_id` обращения (автор): клиент видит только свои. Админ проходит всё
по пермишну `admin`. Роли живут в сиде (`backend/seed/identity.py`), миграции данных не нужно.

## Kafka и лента

События агрегата уходят через outbox той же транзакции в `support.events` (ключ — `ticket_id`):
`SupportTicketOpened`, `SupportMessagePosted` (с `preview` — началом сообщения до 200 символов),
`SupportTicketStatusChanged`. Контракты — `src/core/messaging/contracts/support.py`. Модуль сам ни
на что не подписан.

Ленту строит `notifications` (тип записи `support`, см. [notifications.md](notifications.md)):

- новое обращение и возврат в очередь — роли `underwriter`, «нужно действие», пока обращение не
  взяли или клиент его не закрыл; ссылка `/backoffice/support/{ticket_id}`;
- ответ сотрудника и «взято», «решено», «закрыто» сотрудником — клиенту, одна запись на
  обращение, ссылка `/support/{ticket_id}`;
- сообщение клиента во взятое обращение — сотруднику, который его взял.

## Таблицы

| Таблица | Что |
|---|---|
| `support_tickets` | обращения; индексы по `owner_id`, `organization_id`, `application_id`, `assignee_id`, `(status, updated_at)` |
| `support_messages` | сообщения, FK на обращение с `ON DELETE CASCADE`, UNIQUE `(ticket_id, position)` |

Миграция — `migrations/versions/20261104_1000_support_tickets.py` (`support_0001`, после
`applications_0006`).

## Упрощения

- Списки отдаются массивом без `total`. Для счётчиков («не взятых: 5») понадобится отдельное поле
  или ручка.
- Тексты проходят `SafeString` (nh3): `&` и `<` экранируются. Шаблоны ленты экранируют подстановки
  ещё раз, поэтому `&` из темы в ленте станет `&amp;amp;`. Так ведут себя все тексты ленты.
- Нет вложений, оценки ответа и SLA. Очередь общая на роль, без распределения по сотрудникам.
