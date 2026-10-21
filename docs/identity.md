# Identity: RBAC + ABAC

Модуль входа, аккаунтов и прав. Код — `backend/src/identity`, общая часть доступа — `backend/src/core/access`.
Реализация повторяет access-слой из проекта лида: те же `Permissions`/`Policies`, `AccessContext`, `apply_policies`, `get_access_context_for`.

## Принятые решения

| Вопрос | Решение |
|---|---|
| Регистрация | Нет. Пользователь уже клиент банка (ответ организаторов, `docs/case.md`, раздел 5). Аккаунты создаются через API или bootstrap |
| Вход | Email или телефон + пароль, одна ручка `POST /auth/login`. Телефон нормализуется: `8 (999) 123-45-67` → `+79991234567` |
| Токен | Только access JWT, **RS256**, TTL **30 минут** (`JWT_ACCESS_TTL_MINUTES`). Ни access, ни refresh не храним, refresh нет |
| Проверка токена | По публичному ключу. JWKS отдаётся на `GET /.well-known/jwks.json`, так что проверку можно вынести из Identity |
| Роль | У аккаунта ровно одна роль, одна роль у многих аккаунтов (`accounts.role_id → roles.id`) |
| Права | В роли: `permissions` — массив, `policies` — словарь «пермишн → массив политик» |
| Пермишн | Проверяется на ручке (`get_access_context_for` / `require_permissions`) по claims из токена |
| Политика | Проверяется в репозитории хелпером `apply_policies` |
| `admin` | Пермишн, который обходит все остальные пермишны и политики |
| `own_only` | Только для заявок (Request) и кредитов (Credit/Product): модели наследуют `OwnableMixin`. На аккаунтах её нет |

Следствия «без хранения»: после истечения токена — повторный вход; смена роли или удаление аккаунта вступают в силу, когда истечёт уже выданный токен (максимум 30 минут).

## Модель данных

| Таблица | Поля | Комментарий |
|---|---|---|
| `roles` | `id`, `name` (unique), `description`, `permissions` (JSONB), `policies` (JSONB), `created_at`, `updated_at` | Удалить роль, пока на ней есть аккаунты, нельзя (409) |
| `accounts` | `id`, `email`, `phone`, `password_hash` (argon2id), `role_id`, `created_at`, `updated_at`, `deleted_at` | Нужен email или телефон. Уникальность только среди неудалённых. Удаление мягкое |
| `profiles` | `account_id` (PK), `last_name`, `first_name`, `middle_name`, `position` | 1:1 с аккаунтом |

Пример роли клиента:

```json
{
  "name": "client",
  "permissions": ["requests.read", "requests.create", "credits.read", "profile.update"],
  "policies": {
    "requests.read": ["own_only", "not_deleted"],
    "credits.read": ["own_only"]
  }
}
```

Ключи `policies` обязаны быть в `permissions`, иначе 400. Неизвестный пермишн или политика — 422.

## Политики

| Политика | Миксин | Условие |
|---|---|---|
| `not_deleted` | `DeletedMixin` | `deleted_at IS NULL` |
| `own_only` | `OwnableMixin` | `owner_id = <id из токена>` |

Если на пермишне висит политика, а модель её не поддерживает (например, `own_only` на `accounts.read`), хелпер падает с `ValueError`, а не отдаёт все строки.

## API

| Метод | Путь | Пермишн | Что делает |
|---|---|---|---|
| POST | `/auth/login` | — | `{login, password}` → `{access_token, token_type, expires_in}` |
| GET | `/.well-known/jwks.json` | — | Публичный ключ для проверки токенов |
| GET | `/me` | любой валидный токен | Аккаунт, роль, профиль, пермишны и политики из токена |
| PATCH | `/me/profile` | `profile.update` | Правка своего профиля |
| GET | `/accounts` | `accounts.read` | Список с ABAC-фильтром, `limit`/`offset` |
| GET | `/accounts/{id}` | `accounts.read` | 404, если строка отфильтрована политикой |
| POST | `/accounts` | `accounts.create` | Аккаунт + профиль |
| PATCH | `/accounts/{id}` | `accounts.update` | Email, телефон, пароль, роль, профиль |
| DELETE | `/accounts/{id}` | `accounts.delete` | Мягкое удаление, себя удалить нельзя |
| GET | `/roles`, `/roles/{id}` | `roles.read` | |
| POST | `/roles` | `roles.create` | |
| PATCH | `/roles/{id}` | `roles.update` | Новые права — с новым токеном |
| DELETE | `/roles/{id}` | `roles.delete` | 409, если роль назначена аккаунтам |

Ошибки — `{"code": ..., "message": ...}`: 401 `unauthorized`, 403 `permission_denied`, 404 `not_found`, 409 `conflict`, 400 `bad_request`. Swagger — `/docs`.

## Как подключить права в своём модуле

Модель:

```python
class CreditRequest(UUIDPrimaryKeyMixin, TimestampMixin, OwnableMixin, DeletedMixin, Base):
    __tablename__ = "requests"
    ...
```

Ручка — пермишн проверяется здесь:

```python
@router.get("/requests")
async def list_requests(
    access: Annotated[AccessContext, Depends(get_access_context_for(Permissions.REQUESTS_READ))],
    service: RequestServiceDep,
): ...
```

Репозиторий — политики применяются здесь:

```python
stmt = apply_access_context(select(CreditRequest), CreditRequest, access)
```

При создании записи `owner_id` берётся из токена (`access.user_id` или `CurrentUserId`), не из тела запроса.

`get_current_token` в `core` — порт. В `create_app()` он подменяется на `identity.dependencies.get_current_request_token` через `app.dependency_overrides`. Если модуль уедет в отдельный сервис, туда подставляется своя реализация, которая проверяет токен по JWKS.

## Первый вход

При старте создаются роль `admin` (пермишн `admin`) и аккаунт из `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`, если их ещё нет. Пароль существующего аккаунта не сбрасывается. В compose по умолчанию `admin@example.com` / `Admin-2026!`. Остальные роли и демо-клиентов создаём через API.

## Запуск и проверка

```bash
docker compose up --build        # Postgres + backend, миграции применяются при старте
# http://localhost:8000/docs

cd backend
uv sync
uv run pytest                    # 43 теста, sqlite, Postgres не нужен
uv run ruff check . && uv run ruff format --check .
```

Ключ подписи генерируется при первом старте в volume `jwt-keys` и переживает рестарты. В тестах и локально без Docker — в `backend/keys/` (в `.gitignore`).

## Что не сделано

- События Identity в брокер — брокера в compose пока нет.
- Валидация «политика применима к пермишну» при создании роли — сейчас ошибка конфигурации всплывает только при запросе (fail-loud).
- Отзыв токена до истечения TTL — по решению не храним ничего.
