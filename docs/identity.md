# Identity: RBAC + ABAC

Модуль входа, аккаунтов и прав. Код — `backend/src/identity`, общая часть доступа — `backend/src/core/access`.
Реализация повторяет access-слой из проекта лида: те же `Permissions`/`Policies`, `AccessContext`, `apply_policies`, `get_access_context_for`.

## Принятые решения

| Вопрос | Решение |
|---|---|
| Регистрация | Нет. Пользователь уже клиент банка (ответ организаторов, `docs/case.md`, раздел 5). Аккаунты создают bootstrap (admin), сид (роли и демо-учётки) и API |
| Вход | Email или телефон + пароль, одна ручка `POST /auth/login`. Телефон нормализуется: `8 (999) 123-45-67` → `+79991234567` |
| Токен | Только access JWT, **RS256**, TTL **30 минут** (`JWT_ACCESS_TTL_MINUTES`). Ни access, ни refresh не храним, refresh нет |
| Проверка токена | По публичному ключу. JWKS отдаётся на `GET /.well-known/jwks.json`, так что проверку можно вынести из Identity |
| Роль | У аккаунта ровно одна роль, одна роль у многих аккаунтов (`accounts.role_id → roles.id`) |
| Права | В роли: `permissions` — массив, `policies` — словарь «пермишн → массив политик» |
| Пермишн | Проверяется на ручке (`get_access_context_for` / `require_permissions`) по claims из токена |
| Политика | Проверяется в репозитории хелпером `apply_policies` |
| `admin` | Пермишн, который обходит все остальные пермишны и политики |
| `org_member` | Клиент видит строки компаний, где он участник. Модели наследуют `OrganizationOwnedMixin`, список компаний даёт модуль clients (`docs/platform.md`, «Доступ») |
| Соседи | Читают аккаунты только через `IdentityFacade` (`src/modules/identity/facade.py`) |

Следствия «без хранения»: после истечения токена — повторный вход; смена роли или удаление аккаунта вступают в силу, когда истечёт уже выданный токен (максимум 30 минут).

## Модель данных

| Таблица | Поля | Комментарий |
|---|---|---|
| `roles` | `id`, `name` (unique), `description`, `permissions` (JSONB), `policies` (JSONB), `created_at`, `updated_at` | Удалить роль, пока на ней есть аккаунты, нельзя (409) |
| `accounts` | `id`, `email`, `phone`, `password_hash` (argon2id), `role_id`, `created_at`, `updated_at`, `deleted_at` | Нужен email или телефон. Уникальность только среди неудалённых. Удаление мягкое |
| `profiles` | `account_id` (PK), `last_name`, `first_name`, `middle_name`, `position` | 1:1 с аккаунтом |
| `identity_consents` | `id`, `account_id` (FK, `ON DELETE CASCADE`), `type`, `given_at`, `valid_until`, `revoked_at`, `text_version`, `ip`, `user_agent` | Личные согласия, см. [ниже](#личные-согласия). Строки не перезаписываются |

Роль клиента так, как она лежит в БД:

```json
{
  "name": "client",
  "permissions": ["requests.read", "requests.create", "requests.update", "credits.read",
                  "organizations.read", "organizations.update", "feed.read", "profile.update"],
  "policies": {
    "requests.read": ["org_member"],
    "requests.create": ["org_member"],
    "requests.update": ["org_member"],
    "organizations.read": ["org_member"],
    "organizations.update": ["org_member"]
  }
}
```

Ключи `policies` обязаны быть в `permissions`, иначе 400. Неизвестный пермишн или политика — 422.

## Роли

Роли `client` и `underwriter` создаёт сид `backend/seed/identity.py` (при `SEED_DEMO_DATA=true`), роль `admin` — bootstrap. Сид идемпотентен по имени роли: если роль уже есть, её `permissions`, `policies` и `description` приводятся к объявленным, так что правка роли через API живёт до следующего старта с сидом.

| Пермишн | `client` | `underwriter` | Чей |
|---|---|---|---|
| `requests.read` | ✓ `org_member` | ✓ | applications |
| `requests.create` | ✓ `org_member` | — | applications |
| `requests.update` | ✓ `org_member` | — | applications |
| `credits.read` | ✓ | ✓ | products |
| `organizations.read` | ✓ `org_member` | ✓ | clients |
| `organizations.update` | ✓ `org_member` | ✓ только сверка с реестром | clients |
| `tasks.read`, `tasks.update` | — | ✓ | process |
| `decisions.read` | — | ✓ | decision |
| `backoffice.read` | — | ✓ | bff |
| `feed.read` | ✓ | ✓ | notifications |
| `profile.update` | ✓ | ✓ | identity |

`org_member` рядом с галочкой — политика на этом пермишне. У андеррайтера политик нет: он видит заявки и компании всех клиентов.

## Политики

| Политика | Миксин | Условие |
|---|---|---|
| `not_deleted` | `DeletedMixin` | `deleted_at IS NULL` |
| `own_only` | `OwnableMixin` | `owner_id = <id из токена>` |
| `org_member` | `OrganizationOwnedMixin` | `organization_id IN (<компании, где пользователь участник>)`; нет компаний — нет строк |

Если на пермишне висит политика, а модель её не поддерживает (например, `own_only` на `accounts.read`), хелпер падает с `ValueError`, а не отдаёт все строки.

## Демо-учётки

Сид создаёт 8 учёток из `backend/seed/demo_data.py` (`ACCOUNTS`) с профилем (ФИО и короткая должность). Пароль у всех один — `DEMO_PASSWORD`, по умолчанию `Demo-2026!`. Войти можно по email или по телефону в любом формате (`8 (999) 000-00-01`). Уже существующую учётку сид не трогает и пароль не сбрасывает; если email или телефон занят другим аккаунтом, учётка пропускается.

| Email | Телефон | Роль | Подпись |
|---|---|---|---|
| `owner@romashka.test` | `+79990000001` | `client` | Директор ООО «Ромашка» |
| `accountant@romashka.test` | `+79990000002` | `client` | Бухгалтер ООО «Ромашка» и ИП Иванова |
| `ivanov@ip.test` | `+79990000003` | `client` | ИП Иванов |
| `petrov@vector.test` | `+79990000004` | `client` | Директор ООО «Вектор» (полномочие не подтверждено) |
| `owner@zakat.test` | `+79990000005` | `client` | Директор ООО «Закат» |
| `owner@progress.test` | `+79990000006` | `client` | Директор ООО «Прогресс» |
| `owner@sboy.test` | `+79990000007` | `client` | Директор ООО «Сбой» |
| `underwriter@bank.test` | `+79990000101` | `underwriter` | Андеррайтер |

Админ — `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` (в compose по умолчанию `admin@example.com` / `Admin-2026!`). Компании и участие в них заводит сид модуля clients.

## Вход в один клик (demo-login)

Чтобы эксперты не вводили пароли, есть вход без пароля в демо-учётки — организаторы разрешили «готовый демо-профиль».

- Флаг `DEMO_LOGIN_ENABLED`, по умолчанию `false` (и в `Settings`, и в `docker-compose.yml`). В `.env.example` — `true` для локальной проверки.
- **На публичном стенде флаг выключен.** Ручка выдаёт токен без пароля: включать её там, где стенд доступен из интернета, нельзя.
- Флаг выключен → обе ручки отвечают 404, как будто их нет.
- `POST /auth/demo-login {"login": "owner@romashka.test"}` → тот же ответ, что у `/auth/login`. Логин — email или телефон демо-учётки. Логин не из списка (в том числе admin) или удалённая учётка → 404.
- `GET /auth/demo-accounts` → `[{"login", "phone", "role", "caption", "full_name"}]` — существующие демо-учётки в порядке `demo_data`, без паролей. `caption` — подпись для кнопки («Директор ООО „Ромашка“», «Андеррайтер»).

## API

| Метод | Путь | Пермишн | Что делает |
|---|---|---|---|
| POST | `/auth/login` | — | `{login, password}` → `{access_token, token_type, expires_in}` |
| POST | `/auth/demo-login` | — | `{login}` → токен демо-учётки без пароля; только при `DEMO_LOGIN_ENABLED=true`, иначе 404 |
| GET | `/auth/demo-accounts` | — | Список демо-учёток для кнопок входа; только при `DEMO_LOGIN_ENABLED=true`, иначе 404 |
| GET | `/.well-known/jwks.json` | — | Публичный ключ для проверки токенов |
| GET | `/me` | любой валидный токен | Аккаунт, роль, профиль, пермишны и политики из токена |
| PATCH | `/me/profile` | `profile.update` | Правка своего профиля |
| GET | `/me/consents` | любой валидный токен | Свои личные согласия: действующие и история, новые сверху |
| POST | `/me/consents` | любой валидный токен | `{types: [...]}` → 201, данные согласия |
| DELETE | `/me/consents/{type}` | любой валидный токен | Отзыв; повторный отзыв — тоже 204 |
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

## Фасад для модулей

Другие модули читают аккаунты только через `IdentityFacade` (`src/modules/identity/facade.py`), реализация — `src/modules/identity/facade_impl.py`, регистрируется в `src/modules/identity/module.py::wire`.

| Метод | Что делает |
|---|---|
| `get_account(account_id)` | `AccountRefDTO` (id, email, phone, role_name, ФИО, position) или `None` |
| `find_by_login(login)` | Email в любом регистре или телефон в любом формате — та же нормализация, что у `/auth/login` |
| `verify_password(account_id, password)` | Повторная проверка пароля (step-up перед подписанием) |
| `get_active_consent(account_id, type)` | `ConsentDTO` (`given_at`, `valid_until`, `text_version`) — самое свежее действующее согласие этого типа, или `None`: не давал, отозвал, срок истёк |

Удалённые учётки для фасада не существуют: `get_account` и `find_by_login` возвращают `None`, `verify_password` — `False`.

```python
# в роутере
identity: Annotated[IdentityFacade, Depends(use_facade(IdentityFacade))]
# в обработчике Kafka
identity = ctx.facade(IdentityFacade)
```

В тестах соседей — `tests/fakes/identity_facade.py` (`install(app, IdentityFacade, FakeIdentityFacade())`).

## Личные согласия

Согласие человек даёт за себя, а не за компанию: по 218-ФЗ кредитную историю физлица (руководителя) можно запросить только с его согласия. Согласия компании в заявке (`consents.personal_data`, `consents.credit_bureau`) остаются в applications.

| Тип | Что разрешает | Срок | Редакция текста |
|---|---|---|---|
| `personal_data` | обработку своих ПДн (ст. 9 152-ФЗ) | бессрочно (`valid_until = null`) | `pd-2026-10` |
| `credit_bureau_personal` | запрос своей кредитной истории (ст. 6 218-ФЗ) | 6 календарных месяцев; нет такого числа — последний день месяца | `bki-fl-2026-10` |

- `POST /me/consents` — каждый тип становится новой строкой с `given_at = now`, IP и `User-Agent` запроса. Повторное согласие до истечения не трогает старое: действует самое свежее.
- `DELETE /me/consents/{type}` ставит `revoked_at = now` всем действующим согласиям типа. Истёкшие не трогаются, повторный отзыв ничего не меняет и тоже отвечает 204.
- `active` в ответе — не отозвано и `valid_until` позже текущего момента. Время — по `app.state.clock`.
- Редакции текста — `CONSENT_TEXT_VERSIONS` в `services.py`: новый текст согласия — новая версия там.

Кто читает: процесс при сборке `FetchEnrichment` берёт руководителя по реестру (`ClientsFacade.get_registry_head`) и его `get_active_consent(..., "credit_bureau_personal")`. Есть согласие — в команде `head_bki_consent_at`, и enrichment запрашивает БКИ руководителя; нет — `null`.

## Как подключить права в своём модуле

Модель (пример):

```python
class CreditApplication(UUIDPrimaryKeyMixin, TimestampMixin, OrganizationOwnedMixin, Base):
    __tablename__ = "applications_credit_applications"
    ...
```

Ручка — пермишн проверяется здесь:

```python
@router.get("/applications")
async def list_applications(
    access: Annotated[AccessContext, Depends(get_access_context_for(Permissions.REQUESTS_READ))],
    service: ApplicationServiceDep,
): ...
```

Репозиторий — политики применяются здесь:

```python
stmt = apply_access_context(select(CreditApplication), CreditApplication, access)
```

Для клиента (`org_member`) `get_access_context_for` сам кладёт в `access.organization_ids` его компании, для андеррайтера и admin фильтра нет. Кто действует (`owner_id`, автор) — всегда из токена (`access.user_id` или `CurrentUserId`), не из тела запроса.

`get_current_token` в `core` — порт. В `create_app()` он подменяется на `identity.dependencies.get_current_request_token` через `app.dependency_overrides`. Если модуль уедет в отдельный сервис, туда подставляется своя реализация, которая проверяет токен по JWKS.

## Первый вход

При старте создаются роль `admin` (пермишн `admin`) и аккаунт из `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`, если их ещё нет. Пароль существующего аккаунта не сбрасывается. В compose по умолчанию `admin@example.com` / `Admin-2026!`. Затем при `SEED_DEMO_DATA=true` сид создаёт роли `client`/`underwriter` и демо-учётки (см. выше).

## Запуск и проверка

```bash
docker compose up --build        # миграции и сиды применяются при старте backend
# http://localhost:8000/docs

cd backend
uv sync
uv run pytest                    # sqlite, Postgres не нужен
uv run ruff check . && uv run ruff format --check .
```

Ключ подписи генерируется при первом старте в volume `jwt-keys` и переживает рестарты. В тестах и локально без Docker — в `backend/keys/` (в `.gitignore`).

## Что не сделано

- События Identity в Kafka — соседям хватает фасада.
- Валидация «политика применима к пермишну» при создании роли — сейчас ошибка конфигурации всплывает только при запросе (fail-loud).
- Отзыв токена до истечения TTL — по решению не храним ничего.
