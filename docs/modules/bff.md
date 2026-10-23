# BFF: экраны для фронтенда

Своей БД, событий и фасада у модуля нет: он собирает экраны из фасадов соседей. Клиентские
экраны — `/bff/...` (дашборд, заявки, карточка заявки, подбор продуктов, калькулятор
с предодобрением), экраны бэк-офиса — `/bff/backoffice/...` (очередь андеррайтера, карточка
андеррайтера, метрики). Что отдаёт каждый экран — в [docs/api/client-journey.md](../api/client-journey.md).

## Структура

Раскладка по слоям из [settings/04-module-structure.md](../../settings/04-module-structure.md).

```
bff/
├── module.py                 # register: роутеры client и backoffice; фасада и подписок нет
├── domain/
│   ├── enums.py              # ClientStatus, TodoKind, Segment, PreApprovalBasis,
│   │                         # ConsentKind, ConsentScope (Literal)
│   ├── client_status.py      # статус заявки в терминах фронтенда
│   ├── actions.py            # действия клиента по статусу и правам, пункты «нужно сделать»
│   └── consents.py           # согласия до заявки: название, что даёт, нужно ли для подачи
├── application/
│   ├── dto/                  # organizations, applications, dashboard, products, backoffice
│   ├── interfaces/           # neighbours: Neighbours — фасад соседа, необязательный блок, degraded
│   └── use_cases/            # dashboard; applications (список, карточка); products (подбор,
│                             # калькулятор); backoffice (очередь, карточка, метрики);
│                             # common — видимость компании и сегмент
├── infrastructure/
│   ├── adapters/             # neighbours.py: FacadeNeighbours — фасады из реестра на сессии запроса
│   ├── database/             # пусто: своих таблиц нет
│   └── repositories/         # пусто
└── presentation/
    ├── api/                  # client, backoffice
    ├── schemas/              # client — белый список полей для клиента; backoffice — DTO фасадов как есть
    └── dependencies.py       # сборка use case'ов, права на ручки
```

Своих исключений у модуля нет: use case'ы бросают исключения core (`NotFoundError`,
`ValidationError`), их переводит в ответ общий обработчик.

`domain/actions.py` называет права в компании строками (`submit_application`, `sign`), как их
называет `OrgPermission` в clients: домен не импортирует фасад соседа, он тянет за собой
`clients.application` (контракт «Domain does not depend on application»). Что имена совпадают,
проверяет `tests/bff/test_client_status.py`.

## Как собирается экран

- **Обязательные блоки** (карточка заявки, компания) читаются напрямую: ошибка соседа — ошибка экрана.
- **Необязательные блоки** (лента, новости, решение, скоринг, процесс…) читаются через
  `Neighbours.optional`: если модуль соседа ещё не подключён или источник недоступен
  (`InfrastructureError`), блок остаётся пустым, а его имя попадает в `degraded`. `NotFoundError` —
  «данных нет», не сбой: блок пустой, в `degraded` не попадает.
- Блоки читаются по очереди, а не через `asyncio.gather`: фасады делят сессию запроса.
- **Доступ к компании** проверяется до любого чтения (`use_cases/common.py`): проектор своих
  проверок не делает. Чужая компания — 404, её существование не раскрываем.
- **Что уходит клиенту.** Use case отдаёт DTO, в которых блоки соседей лежат как DTO их фасадов.
  Клиентская схема (`presentation/schemas/client.py`, `from_attributes=True`) перечисляет каждое
  поле и читает только объявленное — балл, факторы скоринга, rule trace, reason codes и данные БКИ
  клиенту не уходят. Бэк-офис получает DTO фасадов целиком.
- Список заявок и счётчики берутся из проектора, карточка и статус одной заявки — из applications:
  клиент сразу видит результат своего действия.

## Согласия на дашборде

`Dashboard.consents` — согласия, которые банк просит до заявки (по схеме — сразу после выбора
условий, до предскоринга), и что даёт каждое. Данные — из `IdentityFacade`, тексты и порядок —
`domain/consents.py`.

| `type` | `scope` | Чьё | `required` |
|---|---|---|---|
| `personal_data` | `account` | того, кто открыл дашборд | да |
| `credit_bureau_company` | `organization` | компании, дал любой представитель | да |
| `credit_bureau_personal` | `account` | только руководителя по реестру | нет |

- `given` — действует сейчас: дано, не отозвано, срок не истёк; `given_at`, `valid_until` — его.
- `required` — без согласия заявку не подать. Черновик и подача берут такие согласия из профиля
  ([applications.md](applications.md#согласия-из-профиля)).
- Дать — `POST /me/consents` для `scope = account` и `POST /organizations/{id}/consents` для
  `scope = organization` ([identity.md](../identity.md#согласия-компании)).
- identity недоступен — блок пустой, в `degraded` — `consents`.
