# BFF: экраны для фронтенда

Своей БД, событий и фасада у модуля нет: он собирает экраны из фасадов соседей. Клиентские
экраны — `/bff/...` (дашборд, заявки, карточка заявки, подбор продуктов, калькулятор
с предодобрением), экраны бэк-офиса — `/bff/backoffice/...` (очередь андеррайтера, карточка
андеррайтера, метрики, сводки скоринга и заявок для админки). Что отдаёт каждый экран — в [docs/api/client-journey.md](../api/client-journey.md).

## Структура

Раскладка по слоям из [settings/04-module-structure.md](../../settings/04-module-structure.md).

```
bff/
├── module.py                 # register: роутеры client и backoffice; фасада и подписок нет
├── domain/
│   ├── enums.py              # ClientStatus, TodoKind, Segment, PreApprovalBasis,
│   │                         # AffordableBy, ConsentKind, ConsentScope (Literal)
│   ├── client_status.py      # статус заявки в терминах фронтенда
│   ├── actions.py            # действия клиента по статусу и правам, пункты «нужно сделать»
│   ├── affordability.py      # платёж, который компания потянет: доля свободного потока
│   ├── consents.py           # согласия до заявки: название, что даёт, нужно ли для подачи
│   └── project_form.py       # с чем открывается форма проектной оценки стартапа у андеррайтера
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
- **Сводка скоринга** (`/bff/backoffice/scoring-overview`, `use_cases/scoring_overview.py`) —
  три запроса вместо карточки на заявку: `ApplicationsFacade.list_submitted` (последние до 1000
  поданных), `ScoringFacade.get_results` и `DecisionFacade.get_decisions` по их id. Счётчики — по
  всем этим заявкам, строки — по последним `limit`. Зоны грейдов — как во встроенной политике
  (A–D зелёная, E–G жёлтая, H–J красная).
- **Сводка заявок** (`/bff/backoffice/applications-overview`, `use_cases/applications_overview.py`) —
  один запрос в проектор (`ProjectorFacade.get_application_stats`): группы «статус × продукт» с
  числом и суммой и корзины сумм считает БД по всем заявкам, BFF складывает из групп воронку
  (докуда заявки дошли), статусы и продукты.

## Калькулятор: посильная сумма

`POST /bff/products/{code}/calculate` отдаёт `max_affordable` — до какой суммы банк готов
предложить на выбранный срок, `affordable_by` — что её ограничило, и `above_affordable` — запрос
больше посильного (заявку это не блокирует: решает специалист).

- **Предодобрение** (`decision`): `max_amount` предложения по продукту. Нет предложения —
  `max_affordable = null`, `above_affordable = false`.
- **Платёжеспособность** (`affordable_by = payment`): платёж не больше 40% свободного потока;
  поток — прибыль по последнему годовому отчёту из `clients` за месяц минус
  `monthly_debt_payments`, без расходов в отчёте — 80% выручки (правило `domain/affordability.py`
  повторяет `decision`, импортировать его bff не может). Сумма ищется под график и срок запроса:
  платёж пропорционален сумме, берём пробу и проверяем через `ProductsFacade.calculate_payment`.
  `max_affordable` — меньшее из двух; причина `amount_above_affordable`, когда запрос выше.
- **Стартап** (`basis = project`): `max_affordable = max_amount` проектного предложения
  (`affordable_by = project`), отчётность не читается.
- Нет годового отчёта — остаётся предодобренный максимум. Платежи по БКИ в расчёт не входят:
  bff их не читает, итог — подсказка, а не обещание.
- `suggestion` урезан до `max_affordable` для урезанного срока.

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

## Стартап

- **Дашборд.** У компании без оборотов (`organization.segment = startup`) блок `startup`: предскрин
  учредителя, `business_plan_revision` (null — план ещё не заполнен) и проектная оценка банка
  (`project`: статус, `max_amount`, ревизия плана, срок, причины — без цифр модели, по ним
  угадываются пороги). В `pre_approved` — только предложение по проектной оценке
  (`basis = project`): предодобрения по оборотам у стартапа нет.
- **Карточка андеррайтера.** У заявки стартапа с проектной оценкой её продукта — блок `startup`:
  оценка с цифрами (`assessment.figures`: DSCR, доля своих, покрытие, сколько выдерживает
  проект), бизнес-план, `plan_changed` (план уточнили после оценки), `valid_at_submission` и
  `form` — с чем открывается форма `project_assessment` (`domain/project_form.py`): оценка
  пройдена и действовала при подаче, сумма в пределах предложения — «одобрить» на запрошенную,
  сверх — встречное на предодобренную, иначе — «отказать»; бизнес-план `acceptable` / `weak`,
  обеспечение и господдержка — из финмодели. Андеррайтер подтверждает или правит.
