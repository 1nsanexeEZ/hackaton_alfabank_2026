# Identity: RBAC + ABAC

Видение лида (21.10.2026) плюс замечания к нему. Замечания помечены **[замечание]**, открытые вопросы собраны внизу.
Предыдущий черновик плана — в истории git (коммит `a150cf5`).

## Контекст

Организаторы в чате трека: предприниматель уже клиент банка, регистрация не нужна, вход можно сделать упрощённым (подробно — `docs/case.md`, раздел 5).
Значит, Identity — это вход, выпуск токена и права. Регистрации, онбординга компании, восстановления пароля нет. Учётки и роли приходят из seed.

## Сущности

| Сущность | Поля | Связи |
|---|---|---|
| `Account` | `id`, логин, данные для входа, `role_id`, `deleted_at` | У аккаунта ровно одна роль |
| `Role` | `id`, `name`, `description`, `permissions`, `policies` | Одна роль у многих аккаунтов (`Account.role_id` → `Role.id`) |

- `permissions` — массив пермишнов.
- `policies` — словарь: ключ — пермишн, значение — массив политик (пустой или с политиками).

```json
{
  "name": "client",
  "description": "Представитель компании-клиента",
  "permissions": ["applications.read", "applications.create", "applications.update"],
  "policies": {
    "applications.read": ["not_deleted", "own_only"],
    "applications.create": [],
    "applications.update": ["not_deleted", "own_only"]
  }
}
```

## core: пермишны, политики, миксины

Пермишны и политики — enum'ы в общем модуле `core`:

```python
from enum import StrEnum


class Permission(StrEnum):
    ADMIN = "admin"
    ACCOUNTS_READ = "accounts.read"
    ACCOUNTS_CREATE = "accounts.create"
    # ... crud-подобные пермишны на каждую сущность


class Policy(StrEnum):
    NOT_DELETED = "not_deleted"  # deleted_at IS NULL
    OWN_ONLY = "own_only"        # owner_id = id текущего юзера
```

На каждую политику — миксин для SQLAlchemy:

| Политика | Миксин | Поле |
|---|---|---|
| `not_deleted` | `SoftDeleteMixin` | `deleted_at` |
| `own_only` | `OwnableMixin` | `owner_id` |

Пермишн `admin`: если он есть, остальные пермишны и политики игнорируются, юзер получает полный доступ.

## Токен

- Только access JWT с коротким TTL. Ни access, ни refresh нигде не храним. Refresh нет.
- Асимметричная подпись, публичные ключи через JWKS, чтобы проверку токена потом можно было вынести из Identity.
- В claims: `sub` (id аккаунта), `permissions`, `policies`, `iat`, `exp`, `kid` в заголовке.

**[замечание] Алгоритм.** RSA и эллиптические кривые — разные алгоритмы. Если хотим эллиптику, берём ES256 (ECDSA P-256): ключи и подписи короче, PyJWT его поддерживает, в JWKS это `kty: "EC"`. Если RSA, то RS256. Предлагаю ES256.

**[замечание] Последствия «без хранения».** Когда токен истёк, нужен повторный вход. Смена роли или блокировка вступают в силу только после истечения токена. Logout — это фронт выбрасывает токен. При коротком TTL это нормально. TTL выносим в env (`ACCESS_TOKEN_TTL_MINUTES`).

## Как проверяем права

1. `get_current_user_id` живёт в Identity и дёргает `TokenAdapter`.
2. В каждом модуле эта функция перегружается.
3. **Пермишн проверяется на ручке**: пермишны и политики достаются из токена.
4. **Политики проверяются на уровне репозитория** хелпером `apply_abac_policies`.

Набросок лида:

```python
from sqlalchemy import Select, Update, Delete


def apply_abac_policies(
    stmt: Select | Update | Delete,
    model: type,
    current_user,
) -> Select | Update | Delete:
    if "own_only" in current_user.policies:
        if issubclass(model, OwnableMixin):
            stmt = stmt.where(model.owner_id == current_user.id)
            return stmt
```

**[замечание] Что поправить в хелпере:**

1. **Политики привязаны к пермишну**, поэтому хелперу нужен пермишн. Иначе непонятно, из какого списка брать политики: `current_user.policies` — это словарь, а не список.
2. **Ранний `return`** внутри `if` пропускает остальные политики. Без политик функция вернёт `None`.
3. **Fail-open.** Если у роли на пермишне висит `own_only`, а у модели нет `owner_id`, фильтр молча не применится и юзер увидит всё. Безопаснее падать с ошибкой конфигурации.
4. **`admin`** обходит фильтры, это тоже стоит учесть в хелпере.

```python
POLICY_FILTERS = {
    Policy.NOT_DELETED: (SoftDeleteMixin, lambda m, u: m.deleted_at.is_(None)),
    Policy.OWN_ONLY: (OwnableMixin, lambda m, u: m.owner_id == u.id),
}


def apply_abac_policies(
    stmt: Select | Update | Delete,
    model: type,
    current_user,
    permission: Permission,
) -> Select | Update | Delete:
    if Permission.ADMIN in current_user.permissions:
        return stmt
    for policy in current_user.policies.get(permission, []):
        mixin, condition = POLICY_FILTERS[policy]
        if not issubclass(model, mixin):
            raise PolicyConfigError(f"{policy} неприменима к {model.__name__}")
        stmt = stmt.where(condition(model, current_user))
    return stmt
```

`.where()` работает и на `Update`, и на `Delete` в SQLAlchemy 2.0, так что хелпер покрывает все три вида запросов.

## Порядок работ

1. Сущность `Role`, связь с `Account` (многие аккаунты → одна роль).
2. Поля роли: `id`, `name`, `description`, `permissions`, `policies`.
3. В `core` — enum'ы пермишнов (crud-подобные: `accounts.read`, `accounts.create` и т.д.) и политик (`not_deleted`, `own_only`).
4. Миксин для каждой политики.
5. Хелпер `apply_abac_policies`.
6. Повесить ограничения на существующие ручки.
7. Пермишн `admin`: полный доступ в обход остальных пермишнов и политик.

Сюда же: выпуск JWT с JWKS, `TokenAdapter`, `get_current_user_id`, seed ролей и демо-аккаунтов.

## Открытые вопросы

| # | Вопрос | Предложение |
|---|---|---|
| 1 | ES256 или RS256? | ES256 |
| 2 | TTL access? | 30 мин, через env |
| 3 | Как входим: логин и пароль из seed, телефон без кода (SMS запрещены кейсом), кнопка «войти как демо-клиент»? | Логин и пароль из seed плюс кнопки демо-учёток на странице входа |
| 4 | Где фронт держит токен: память, `localStorage` или httpOnly-cookie через BFF? | httpOnly-cookie через BFF, токен в браузерный JS не попадает |
| 5 | `own_only` фильтрует по `owner_id = id аккаунта`. Если у компании будет несколько представителей, они не увидят заявки друг друга | Для MVP ок (один демо-профиль на компанию). Если понадобится, добавить политику `own_company` по `company_id` |
| 6 | Роли в seed | `client` (заявки с `own_only`), `analyst` (все заявки, без `own_only`), `admin` (пермишн `admin`) |
