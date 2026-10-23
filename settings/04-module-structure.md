# 04. Структура модуля бэкенда

## Правило

Каждый модуль в `backend/src/modules/<module>/` устроен одинаково. Эталон — `identity`.

```
<module>/
├── __init__.py
├── facade.py               Protocol + frozen DTO — всё, что модуль отдаёт соседям
├── module.py               register(app), wire(app), subscribers(), при нужде startup/shutdown
├── domain/                 чистый Python: сущности, правила, доменные исключения
│   ├── __init__.py
│   ├── <aggregate>.py      агрегаты (account.py, profile.py, …)
│   ├── entities.py         остальные сущности
│   ├── enums.py            перечисления и справочники
│   ├── events.py           доменные события — только если они есть
│   ├── exceptions.py       доменные исключения, без HTTP
│   └── <policy>.py         правила, которые не принадлежат одной сущности (login_policy.py, …)
├── application/
│   ├── __init__.py
│   ├── dto/                входы и выходы use cases: frozen dataclass
│   ├── interfaces/         Protocol: репозитории, внешние сервисы, токены, хешер
│   └── use_cases/          один класс на операцию, метод execute()
├── infrastructure/
│   ├── __init__.py
│   ├── adapters/           реализации интерфейсов (JWT, argon2, HTTP-клиенты, facade_impl)
│   ├── database/           ORM-модели (models.py), таблицы с префиксом модуля
│   ├── repositories/       реализации репозиториев + мапперы ORM <-> domain
│   └── exception_handler.py  доменные исключения -> HTTP-ответ
└── presentation/
    ├── __init__.py
    ├── api/                роутеры FastAPI
    ├── schemas/            pydantic-схемы запросов и ответов
    └── dependencies.py     сборка use cases для роутеров (DI)
```

- Папки из дерева обязательны. Пока папка пустая — кладём в неё `.gitkeep`.
- Файлы внутри `domain/` заводим по содержанию: нет событий — нет `events.py`.
- `facade.py` и `module.py` остаются в корне: на них опираются `main.py`, соседи и import-linter.

## Слои и зависимости

Зависимости идут только внутрь: `presentation` и `infrastructure` → `application` → `domain`.

| Слой | Что можно | Чего нельзя |
|---|---|---|
| `domain` | Python, `src.core.domain`, перечисления прав из `src.core.access` | FastAPI, SQLAlchemy, Pydantic, httpx, брокер; `application`, `infrastructure`, `presentation` |
| `application` | `domain`, свои `interfaces` и `dto`, `src.core.uow.UnitOfWork`, `Clock` | конкретные адаптеры, ORM-модели, `AsyncSession`, pydantic-схемы, `seed` |
| `infrastructure` | всё, что ниже; SQLAlchemy, внешние библиотеки | `presentation` |
| `presentation` | `application` (use cases, dto), `domain` (валидаторы), сборку адаптеров в `dependencies.py` | бизнес-правила, прямые запросы в БД из роутера |

Границы проверяет import-linter (`uv run lint-imports`, контракты в `backend/pyproject.toml`).

## SOLID на практике

- **Интерфейс + адаптер.** Всё внешнее (БД, JWT, хеширование паролей, HTTP, хранилище, каталоги из `seed`) use case получает через `Protocol` из `application/interfaces/`. Реализация лежит в `infrastructure/adapters/` или `infrastructure/repositories/` и явно наследует свой Protocol (`class JwtTokenService(TokenService)`), чтобы mypy проверял сигнатуры прямо в адаптере.
- **Один use case — один класс.** `CreateRoleUseCase`, `LoginUseCase`… с методом `execute()`, в конструкторе только нужные интерфейсы. Файлы группируем по области: `use_cases/roles.py`, `use_cases/auth.py`.
- **Транзакции** — через `UnitOfWork` (`src/core/uow.py`), а не `session.commit()` в use case.
- **DTO отдельно.** `application/dto/` — frozen dataclass, без pydantic. Pydantic живёт только в `presentation/schemas/`, ORM — только в `infrastructure/database/`. Роутер переводит схему запроса в DTO, use case возвращает DTO, роутер отдаёт схему ответа (`model_validate(dto)` с `from_attributes=True`).
- **PATCH.** «Поле не прислали» и «прислали null» различаем сентинелом `UNSET` в DTO; presentation собирает DTO из `model_dump(exclude_unset=True)`.
- **Исключения.** Домен бросает свои исключения без HTTP-статусов. `infrastructure/exception_handler.py` переводит их в ответ того же формата, что у core (`{code, message}`), и регистрируется в `module.register(app)`.
- **Домен без ORM.** Репозиторий отдаёт и принимает доменные сущности; ORM-модели наружу из `infrastructure` не выходят.

## Как перевести модуль

1. Ветка `feature/<issue>-<module>-layers` от `develop` (см. [02-branches.md](02-branches.md)).
2. `api/` → `presentation/api/`, схемы → `presentation/schemas/`, `api/dependencies.py` → `presentation/dependencies.py`.
3. `application/ports.py` → `application/interfaces/`; `service.py`, `commands.py` → `application/use_cases/` (класс на операцию); DTO → `application/dto/`.
4. `infrastructure/models.py` → `infrastructure/database/models.py`, обновить импорт в `backend/src/models.py`.
5. `infrastructure/facade_impl.py` и клиенты внешних систем → `infrastructure/adapters/`; репозитории → `infrastructure/repositories/`.
6. Исключения модуля → `domain/exceptions.py` + `infrastructure/exception_handler.py`.
7. HTTP-контракт и схема БД не меняются: тесты модуля проходят без правок, кроме импортов; `uv run alembic check` — без изменений.
8. Проверка: `uv run pytest -q`, `uv run lint-imports`, `uv run ruff check .`, `uv run mypy src/modules/<module>`.

Один модуль — одна ветка и один PR.
