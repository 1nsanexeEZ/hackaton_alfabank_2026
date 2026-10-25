# Модуль `process`

## Зачем

Движок маршрутов заявки. Маршрут продукта описан в BPMN (`express_v2`, `standard_v2`, `secured_v2`,
`mortgage_v2`, `startup_v2`): какие шаги идут друг за другом, какие ветки у шлюзов, где ждать
человека. На каждую поданную заявку движок заводит один экземпляр процесса, шлёт команды модулям
(`enrichment`, `scoring`, `decision`), ждёт ответа именно на свою команду, ставит задачи
андеррайтеру и публикует события `process.events`. Статусы самой заявки — в
[state-machine.md](../state-machine.md). Код — `backend/src/modules/process`.

Маршруты `*_v2` (#143) — это `*_v1` с шагом «Стоп-факторы» как на общей схеме: после обогащения
`check_stop_factors` шлёт `CheckStopFactors` в decision и ждёт `StopFactorsPassed` или
`DecisionMade`. Шлюз `gw_stop`: стоп-фактор сработал (`stopped == true`) — сразу на шлюз исхода
`gw_outcome` (отказ или, у ИП без согласия на авторешение, андеррайтер), скоринг не вызывается;
нет — дальше по маршруту v1. Продукты переведены на `*_v2`; `*_v1` остаются, чтобы уже идущие
процессы дошли по своему маршруту.

## Структура

Раскладка по слоям из [settings/04-module-structure.md](../../settings/04-module-structure.md).

```
process/
├── facade.py                 # ProcessFacade + реэкспорт DTO и Literal-типов для соседей;
│                             # реализация — infrastructure/adapters/process_facade.py
├── module.py                 # register: роутер; wire: каталог маршрутов, фасад и порт
│                             # WorkflowSource; startup/shutdown: фоновая задача таймаутов
├── workflows/*.bpmn          # маршруты продуктов — данные, не код (см. ниже)
├── domain/
│   ├── process.py            # агрегат ProcessInstance: проход по графу, ожидание, таймауты
│   ├── steps.py              # закрытый реестр шагов STEPS, Trigger, факты и порт ProcessFacts
│   ├── tasks.py              # UserTask — задача сотрудника банка
│   ├── workflow.py           # граф маршрута: узлы, переходы, настройки узла
│   ├── conditions.py         # язык условий на переходах шлюзов (без eval)
│   ├── validation.py         # проверка маршрута при загрузке
│   ├── context.py            # ProcessContext — то, что процесс запомнил по ходу
│   ├── events.py             # доменные события процесса
│   ├── enums.py              # NodeType, OnFailure, StepKind, ProcessStatus, WaitKind, TaskStatus
│   └── exceptions.py         # ConditionError, WorkflowValidationError (ошибки загрузки маршрута)
├── application/
│   ├── dto/                  # processes, tasks (фасад и API), workflows
│   ├── interfaces/           # repositories, workflows (WorkflowSource), outbox (MessageOutbox),
│   │                         # transactions (ProcessTransaction для фоновой задачи)
│   ├── mappers/              # messages: события и команды ↔ контракты; views: домен → DTO
│   └── use_cases/            # processes (старт, ход, отмена, таймаут), tasks (API андеррайтера),
│                             # views (фасад и чтение для API), workflows, timeouts; common — публикация
├── infrastructure/
│   ├── adapters/             # process_facade, application_facts (ProcessFacts через фасады),
│   │                         # workflow_catalog (WorkflowSource), process_transaction, task_unit_of_work
│   ├── bpmn.py               # разбор BPMN (lxml) в WorkflowDefinition
│   ├── database/             # models
│   └── repositories/         # processes, tasks, mappers
└── presentation/
    ├── api/                  # tasks, processes, workflows
    ├── schemas/              # pydantic-схемы по тем же темам
    ├── consumers.py          # подписки на applications.events и ответы модулей
    ├── timeouts.py           # фоновая задача: шаги, которые ждут ответа слишком долго
    └── dependencies.py       # сборка use case'ов для роутеров, обработчиков, задачи и фасада
```

- **`workflows/` остаётся в корне модуля.** BPMN-файлы — данные: их грузит
  `infrastructure/adapters/workflow_catalog.py` (`WORKFLOWS_DIR`), на этот путь опираются тесты,
  фронт разбирает XML и рисует граф маршрута (`GET /workflows/{code}/diagram`). Битый файл останавливает старт
  приложения списком проблем.
- **`bpmn.py` — не адаптер порта.** Разбор BPMN нужен только инфраструктуре: каталогу маршрутов и
  репозиторию процессов (снимок графа из БД). Use case'ы получают уже готовый `WorkflowDefinition`
  через `WorkflowSource`.
- **Порт фактов в домене.** Шаги читают данные заявки через `ProcessFacts` (`domain/steps.py`), поэтому
  протокол живёт в домене; реализация `ApplicationFacts` ходит в фасады `applications`, `clients`,
  `identity`.
- Своих HTTP-исключений нет: `UserTask` и use case'ы бросают исключения core (`NotFoundError`,
  `ConflictError`, `PermissionDeniedError`…), их переводит общий обработчик, поэтому
  `infrastructure/exception_handler.py` не заведён.

## Транзакции

| Где | Кто коммитит |
|---|---|
| Kafka-обработчики (`consumers.py`) | ядро: `MessageProcessor` коммитит процесс, исходящие команды и события вместе с отметкой инбокса. Use case'ы `StartProcessUseCase`, `HandleTriggerUseCase`, `CancelProcessUseCase` не коммитят |
| HTTP (`claim`, `complete`) | use case через `UnitOfWork`. `TaskUnitOfWork`: если задачу успел поменять кто-то другой (`StaleDataError` на коммите) — `409` с `details.code = version_conflict` |
| Фоновая задача таймаутов | `TimeOutStuckStepsUseCase`: на каждую заявку своя `ProcessTransaction` (своя сессия). Если процесс в это время сдвинул ответ модуля, транзакция откатывается (`StaleProcessError`), заявка пропускается |

Закрытие задачи андеррайтером и следующий шаг процесса идут в одной транзакции.

## API

Права — `tasks.read` / `tasks.update`.

| Метод | Путь | Что |
|---|---|---|
| GET | `/tasks` | очередь задач по сроку: `role` (по умолчанию `underwriter`), `status` (`active` = open + in_progress) |
| GET | `/tasks/{task_id}` | задача и процесс её заявки |
| POST | `/tasks/{task_id}/claim` | взять задачу |
| POST | `/tasks/{task_id}/complete` | решение андеррайтера (комментарий обязателен), закрывает только исполнитель |
| GET | `/processes/{application_id}` | где заявка в маршруте: шаги, `visited_node_ids` для подсветки пути, `manual_review_reason` |
| GET | `/workflows` | загруженные маршруты |
| GET | `/workflows/{code}/diagram` | BPMN XML: по нему бэк-офис рисует граф маршрута |

Экран бэк-офиса читает очередь из `projector`, эти ручки — для работы с задачей и схемы маршрута.

**Почему задача у андеррайтера.** У задачи есть `reason`, у процесса — `manual_review_reason`:
причина, по которой заявка у человека, помимо кодов причин самого решения. Это ручное решение,
которое decision не принял (`ManualDecisionRejected`: «Ручное решение не принято: …» с текстом
decision), или шаг, который упал или повторился больше `max_iterations` раз. `null` — заявку отдало
человеку само решение (MANUAL_REVIEW). У процесса причина сбрасывается, когда андеррайтер закрывает
задачу; у задачи остаётся. Обе видны и в карточке `/bff/backoffice/applications/{id}` (`process`,
`task`).

## Kafka

| Топик | Группа | Что делает |
|---|---|---|
| `applications.events` | `process.applications-events` | `ApplicationSubmitted` — старт, `ApplicationCancelled` — отмена, события клиента (`ApplicationInfoProvided`, `OfferAccepted`, `OfferDeclined`, `OfferExpired`, `ApplicationSigned`) — ход процесса |
| `enrichment.events`, `scoring.events`, `decision.events` | `process.<topic>` | ответы на команды (`StopFactorsPassed` — тоже); принимается только ответ с `causation_id` = id отправленной команды |

Команды и события `process.events` уходят через outbox той же транзакции.

## Фасад

`ProcessFacade`: `get_process_view(application_id)`, `list_open_tasks(role, limit, offset)`,
`get_task(task_id)`, `workflow_codes()`. Читают `bff` и `projector`; `workflow_codes` — `products`: маршрут нового или изменённого продукта должен быть среди загруженных BPMN.
