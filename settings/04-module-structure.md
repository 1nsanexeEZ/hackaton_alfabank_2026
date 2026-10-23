# 04. Структура модуля

## Правило

Все модули в `backend/src/modules/<module>/` устроены одинаково — по слоям чистой архитектуры.
Зависимости направлены только внутрь: **presentation → infrastructure → application → domain**.
Эталон — модуль `enrichment`.

```
<module>/
├── __init__.py
├── facade.py                  # публичный контракт для соседей: Protocol + реэкспорт DTO
├── module.py                  # сборка модуля: register / wire / subscribers
├── domain/                    # чистый Python: без FastAPI, SQLAlchemy, pydantic, httpx
│   ├── __init__.py
│   ├── <aggregate>.py         # агрегаты: account.py, snapshot.py …
│   ├── entities.py            # сущности и value objects вне агрегатов
│   ├── enums.py               # перечисления и Literal-типы
│   ├── events.py              # доменные события
│   ├── exceptions.py          # доменные ошибки
│   └── <rule>_policy.py       # бизнес-правила: login_policy.py, consent_policy.py …
├── application/
│   ├── __init__.py
│   ├── dto/                   # DTO: dataclass'ы без логики, по файлу на тему
│   ├── interfaces/            # порты (Protocol): репозитории, внешние источники, кеши, парсеры
│   └── use_cases/             # сценарии: один класс — один сценарий, метод `execute`
├── infrastructure/
│   ├── __init__.py
│   ├── adapters/              # реализации портов: HTTP-клиенты, файлы, кеш, брокер
│   ├── database/              # SQLAlchemy-модели, мапперы запись ↔ домен, сериализация
│   ├── repositories/          # реализации репозиториев из application/interfaces
│   ├── config.py              # настройки модуля (pydantic-settings)
│   └── exception_handler.py   # ошибки → HTTP-ответы
└── presentation/
    ├── __init__.py
    ├── api/                   # FastAPI-роутеры
    ├── schemas/               # pydantic-схемы запросов и ответов
    ├── consumers.py           # обработчики команд и событий из Kafka
    ├── facade_impl.py         # реализация facade.py: только зовёт use case'ы
    └── dependencies.py        # сборка use case'ов из реализаций (DI)
```

Пустое не заводим: нет HTTP API — нет `api/`, `schemas/`, `exception_handler.py`; нет настроек —
нет `config.py`.

## Кто что импортирует

| Слой | Можно | Нельзя |
|---|---|---|
| `domain` | stdlib, `src.core.domain` | остальные слои, фреймворки, DTO |
| `application` | `domain`, `src.core`, фасады соседей (`src.modules.<other>.facade`) | `infrastructure`, `presentation`, `module` |
| `infrastructure` | `application`, `domain`, `src.core`, библиотеки | `presentation`, `module`, свой `facade.py` |
| `presentation` | всё своё, кроме `module` | — |
| `facade.py` | `application/dto`, `domain/enums` | — |
| `module.py` | всё своё | — |

Внутри модуля DTO берём из `application/dto/`, а не из `facade.py`. Другие модули — наоборот,
только из `facade.py`: в `domain`, `application`, `infrastructure`, `presentation` чужого модуля
не ходим.

## SOLID — как это выглядит в коде

- **S** — один use case = один сценарий. Фасад и обработчики Kafka без логики: собрали use case и
  вызвали. Правило предметной области — отдельной функцией в `domain/<rule>_policy.py`.
- **O** — новый источник, хранилище или формат файла = новый адаптер; use case не меняется.
- **L** — адаптер и тестовый фейк реализуют один и тот же Protocol и взаимозаменяемы.
- **I** — узкие порты: `RegistrySource.fetch(inn)`, а не один клиент «на всё».
- **D** — use case получает порты в конструкторе. Конкретные реализации подставляет только
  `presentation/dependencies.py` (и `module.py` для того, что живёт весь процесс).

## DTO

- DTO лежат в `application/dto/` — frozen dataclass без логики (вычисляемое свойство допустимо).
- Домен DTO не знает: у него свои сущности и value objects. DTO ↔ домен переводит application
  (маппер рядом с use case'ом).
- Соседям DTO отдаёт `facade.py` модуля — реэкспортом из `application/dto/`.
- Если DTO попадает в pydantic-схему и поле названо как свой тип (`date: date`), в его файле не
  пишем `from __future__ import annotations` — иначе pydantic не соберёт схему.

## Как перевести модуль

1. Ветка `feature/<номер ишью>-<module>-refactor` (общая ишью рефактора — #81).
2. Разложить файлы по слоям через `git mv`, чтобы сохранить историю.
3. Вынести DTO в `application/dto/`, порты — в `application/interfaces/`, сценарии — в
   `application/use_cases/`; домен очистить от DTO и контрактов сообщений.
4. Логику из `facade_impl` и обработчиков перенести в use case'ы; сборку — в
   `presentation/dependencies.py`.
5. Добавить модуль в `containers` контракта «Layered modules» в `backend/pyproject.toml`.
6. Обновить `docs/modules/<module>.md`.
7. Поведение, HTTP API и схема БД не меняются: `ruff check`, `ruff format --check`,
   `lint-imports`, `pytest` зелёные.

Какие модули уже переведены — список `containers` того же контракта.

## Для агентов

- Новый код в модуле кладём по этой структуре. Если модуль ещё старый — не смешиваем перенос
  файлов с фичей в одном PR: сначала рефактор модуля отдельной веткой, потом фича.
- Структуру проверяет `uv run lint-imports`; сломанный контракт не обходим через `ignore_imports`.
