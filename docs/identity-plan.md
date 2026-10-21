# План: сервис Identity (финальный)

Источники: черновики MVP, Enterprise и Authz, критика к ним, `docs/architecture/architecture.md`, `docs/case.md`, `docs/chat-insights.md`.
Сегодня 21.10. Сдаём 25.10, за сутки до дедлайна (26.10, 18:00 МСК). Бюджет Identity: около 22 ч на одного человека плюс 4 ч на `libs/authz` у второго.

Развилки помечены **Р1, Р2…** в формате «решение / альтернатива / почему». По этим номерам удобно спорить.

---

## 1. TL;DR

- Identity — отдельный FastAPI-сервис со своей схемой в общем Postgres. Вход: логин и пароль, access JWT RS256 на 10 минут, refresh с ротацией в httpOnly-cookie у BFF. Браузер JWT не видит.
- Права проверяются **локально в каждом сервисе** общей библиотекой `libs/authz`: claims из JWT плюс атрибуты ресурса из своей БД. Во время работы в Identity никто не ходит, кроме BFF (вход) и загрузки JWKS.
- RBAC: матрица в `roles.yaml`. ABAC: около 10 правил на Python с кодами отказа. Списки фильтруются через `scope_filter`. Чужой объект даёт 404, нехватка прав внутри своей компании даёт 403 `{code, message}`.
- Роли клиента выдаются в разрезе компании: `org_admin`, `org_finance`, `org_operator` плюс атрибуты `can_sign`, `amount_limit`, `valid_until`. Роли банка: `bank_analyst`, `bank_head`, `bank_admin`.
- Права отзываются до истечения TTL через `authz_version` в токене и событие `identity.user.authz_changed` в брокер.
- Seed: 12 демо-учёток с фиксированными UUID и синтетическими ИНН (код региона `00`), кнопки «Войти как…», защита демо-учёток на стенде.
- Must около 15,5 ч, Should около 7,5 ч. При нехватке времени режем онбординг, step-up и события. Изоляцию компаний, ABAC-лимиты и seed не режем.

---

## 2. Границы

| В Identity | Не в Identity | Где живёт |
|---|---|---|
| Учётки клиентов и сотрудников банка, статус, блокировка | Заявки, статусы, `assigned_to`, история шагов | Request |
| Вход, сессии, refresh, JWKS, step-up | Финпоказатели, документы, анкета | Request |
| Профиль человека: ФИО, телефон, должность, `pd_consent_at` | Согласие на запрос в БКИ: чекбокс на конкретную заявку | Request, передаётся в событии `application.submitted` |
| Организация как арендатор (tenant): ИНН, ОГРН, форма, название, ОКВЭД, регион, дата регистрации, `registry_status`, `verification` | Данные ЕГРЮЛ/ЕГРИП, «Прозрачный бизнес», БКИ | Мок-сервис `ext-mocks` (внешняя система вне периметра) |
| Членство user↔org: роль и атрибуты полномочий | Скоринг, кредитное решение, кредитный лимит клиента | Scoring |
| Сотрудник банка: роль и **лимит полномочий** на одобрение | Подписание как операция | Request (Identity даёт только step-up) |
| `roles.yaml`, ABAC-правила, `scope_filter` (в `libs/authz`) | Новостная лента | Отдельный модуль или BFF (атрибуты организации берёт из событий Identity) |
| Свой append-only `audit_log` | Аудит переходов заявки и решений | Свой `audit_log` в Request и Scoring того же формата |

Два разных лимита не путаем: лимит полномочий сотрудника хранит Identity, кредитный лимит клиента считает Scoring.

Identity вызывает `ext-mocks` (`GET /egrul/{inn}`) один раз, при привязке компании. В `architecture.md`, вопрос 4, нужно дописать Identity в список тех, кто вызывает мок.

**Р1. Сервис или модуль.** Решение: отдельный контейнер `identity`, общий код только в `libs/authz` (uv workspace в `backend/`). Альтернатива: модуль одного FastAPI-приложения, тогда проще отладка, а HS256 и `fresh`-чтение БД становятся возможны. Почему сервис: так решено в `architecture.md` (вопрос 13) и так нарисовано на схеме, а переключаться посреди работы дороже. Но `case.md` упоминает один `backend/Dockerfile`, поэтому лиду стоит подтвердить.

---

## 3. Подмодули

| Подмодуль | Ответственность |
|---|---|
| **Auth** | `login`, `refresh` (ротация и обнаружение повторного использования), `logout`, `switch-org`, `step-up`; блокировка после неудачных попыток; выпуск JWT, ключи и JWKS; регистрация клиента |
| **Account** | Таблица `users`: логин, хэш пароля, `kind`, `status`, `is_demo`, `authz_version`. Сотрудники банка и их `approval_limit`. Блокировка и разблокировка, сброс пароля админом банка (Could) |
| **Profile** | ПДн человека (только здесь). Карточка организации, привязка по ИНН через мок ЕГРЮЛ, симуляция подтверждения полномочий «через Госуслуги Бизнес» |
| **ACL** | Членства и их атрибуты, роли банка, отдача эффективных прав в `/me`, свой `audit_log`. Логика решений (`check`, `authorize`, `scope_filter`) лежит в `libs/authz`, Identity её использует так же, как остальные сервисы |

---

## 4. Модель данных

Postgres 16, схема `identity`, роль БД `identity_app`. У этой роли нет прав на чужие схемы, а на `audit_log` только `INSERT` и `SELECT`.

| Таблица | Ключевые поля | Связи и комментарий |
|---|---|---|
| `users` | `id uuid`, `login citext unique`, `password_hash`, `kind` (client/employee), `status` (active/blocked), `is_demo bool`, `authz_version int`, `failed_logins`, `locked_until`, `last_login_at`, `created_at` | `authz_version` растёт при любой смене прав |
| `profiles` | `user_id` PK/FK, `last_name`, `first_name`, `middle_name`, `phone`, `position`, `pd_consent_at`, `updated_at` | 1:1 с `users`. Единственное место с ПДн |
| `employees` | `user_id` PK/FK, `employee_no`, `department`, `approval_limit numeric`, `active` | Только для `kind=employee` |
| `user_roles` | `user_id`, `role_code`, `granted_by`, `granted_at` | Роли банка. `role_code` сверяется с `roles.yaml` |
| `organizations` | `id uuid`, `inn unique`, `ogrn`, `kpp null`, `legal_form` (ip/ooo/ao), `name`, `okved_main`, `region`, `registered_on`, `registry_status` (active/liquidated), `verification` (unverified/verified), `verified_via` (seed/gosuslugi_sim), `verified_at`, `created_by` | Карточка нужна шапке, ленте и правилу R5 |
| `memberships` | `id`, `user_id`, `org_id`, `role_code`, `position`, `can_sign bool`, `amount_limit numeric null`, `valid_until null`, `basis` (seed/gosuslugi_sim/admin_grant), `status` (active/revoked), `granted_by`, `created_at`, `revoked_at`; `unique(user_id, org_id)` | Основа ABAC для клиента. Должность — не роль |
| `sessions` | `id` (= `sid`), `user_id`, `active_org_id null`, `refresh_hash`, `prev_refresh_hash`, `rotated_at`, `expires_at`, `revoked_at`, `revoke_reason`, `ip`, `user_agent` | Одна строка на сессию, подробнее в п. 6 |
| `audit_log` | `id bigserial`, `occurred_at`, `actor_id`, `actor_kind`, `org_id`, `session_id`, `action`, `target_type`, `target_id`, `result` (success/fail/deny), `reason`, `ip`, `request_id`, `details jsonb` (без ПДн) | Append-only. Формат общий для всех сервисов |
| `outbox` | `id`, `event_type`, `payload jsonb`, `created_at`, `published_at`, `attempts` | Пишется в той же транзакции, что и изменение |

**Р2. Где хранить роли и права.** Решение: единственный источник правды — `libs/authz/roles.yaml`, таблиц `roles`, `permissions` и `role_permissions` нет. Таблица прав в README генерируется из YAML. Альтернатива: таблицы, засеянные из YAML, ради FK и SQL-отчётов. Почему YAML: один источник и ноль синхронизации. FK на роль экспертам ничего не даёт.

**Р3. Таблица политик.** Решение: таблицы нет, правила пишутся кодом (policy-as-code) и покрываются тестами. Альтернатива: `policies` с JSON-условиями или OPA. Почему: интерпретатор условий за 4 дня не окупится. Сравнение «самописный слой, Casbin, OPA, OpenFGA» фиксируем в `docs/decisions.md`. Интерфейс `check(subject, action, resource) -> Decision` совместим с OPA (критерий 06).

Сознательно не делаем: `consents` (согласие на БКИ относится к заявке), `invitations`, `service_clients`, `signing_keys`, `refresh_tokens` отдельной таблицей, цепочку хэшей в аудите.

---

## 5. Модель доступа

### 5.1 Роли клиента (в разрезе компании, через `memberships`)

| Роль | Кто обычно | Суть |
|---|---|---|
| `org_admin` | Собственник, гендиректор, ИП | Всё, включая управление участниками |
| `org_finance` | Финдиректор, бухгалтер | Готовит и подаёт заявки в пределах `amount_limit` |
| `org_operator` | Сотрудник по финансированию | Черновики, документы, ответы на запросы банка. Подать заявку не может |

Атрибуты членства не зависят от роли. `can_sign` — право подписи (ЕИО или доверенность/МЧД, в демо задаётся seed или симуляцией). `amount_limit` — лимит суммы, `null` означает без лимита. `valid_until` — срок доверенности.

### 5.2 Роли банка (глобальные, через `user_roles`)

| Роль | Суть | Атрибут |
|---|---|---|
| `bank_analyst` | Берёт заявки из очереди, запрашивает информацию, принимает решение в пределах лимита | `approval_limit` (3 млн в seed) |
| `bank_head` | Решения выше лимита аналитика, назначение, override отказа скоринга с обязательной причиной | `approval_limit` (20 млн) |
| `bank_admin` | Пользователи, блокировки, журнал аудита. **Заявки не видит** (разделение обязанностей, SoD) | — |

**Р4. Набор ролей.** Решение: 3 роли клиента и 3 роли банка, аудитор объединён с админом, `org_viewer` не делаем. Альтернатива: добавить `bank_manager` (клиентский менеджер: очередь и назначение без права решения) и отдельного `auditor`. Почему: каждая роль — это ещё учётка, колонка в матрице и тесты. `bank_manager` нужен, только если в UI сотрудника будет отдельный экран назначения (вопрос В3).

### 5.3 RBAC-матрица (`roles.yaml`)

| Право | org_admin | org_finance | org_operator | bank_analyst | bank_head | bank_admin |
|---|---|---|---|---|---|---|
| `application.read` | + | + | + | + (очередь) | + | – |
| `application.create`, `application.edit` | + | + | + | – | – | – |
| `application.submit` | + | + (R3) | – | – | – | – |
| `application.withdraw` | + | – | – | – | – | – |
| `application.answer_info`, `documents.upload` | + | + | + | – | – | – |
| `offer.accept`, `document.sign` | + (R4) | + (R4) | – | – | – | – |
| `org.read` | + | + | + | – | – | – |
| `org.members.manage` | + | – | – | – | – | – |
| `application.take` | – | – | – | + | + | – |
| `application.assign` | – | – | – | – | + | – |
| `application.request_info` | – | – | – | + (R7) | + | – |
| `scoring.read_summary` | + | + | + | + | + | – |
| `scoring.read_details` | – | – | – | + | + | – |
| `decision.make` | – | – | – | + (R7, R8) | + (R8) | – |
| `decision.override` | – | – | – | – | + (R9, R10) | – |
| `user.manage`, `audit.read` | – | – | – | – | – | + |

Роль задаёт потолок прав, атрибуты его сужают. Например, `org_operator` с `can_sign=true` всё равно не подписывает: у его роли нет права `document.sign`.

### 5.4 ABAC-правила (`libs/authz/rules.py`)

| # | Действие | Условие | Отказ |
|---|---|---|---|
| R1 | Любое клиентское по объекту | `resource.org_id == token.org`, членство `active`, `valid_until` не истёк | **404** |
| R2 | `application.edit` | `status ∈ {draft, info_requested}` | 403 `STATUS_FORBIDS` |
| R3 | `application.submit` | `status = draft`, `amount <= membership.amount_limit` (или лимит `null`) | 403 `AMOUNT_LIMIT_EXCEEDED` |
| R4 | `offer.accept`, `document.sign` | `can_sign`, `valid_until` не истёк, статус `offer`/`signing`; если step-up включён, то `reauth ∈ amr` и `now - auth_time <= 300 с` | 403 `SIGN_RIGHT_REQUIRED` / `STEP_UP_REQUIRED` |
| R5 | `application.create`, `application.submit` | `org.registry_status = active` и `org.verification = verified` | 403 `ORG_INACTIVE` / `ORG_NOT_VERIFIED` |
| R6 | Любое банковское чтение | `status ≠ draft`: черновики клиента банку не видны | **404** |
| R7 | `request_info`, `decision.make` (аналитик) | `resource.assigned_to == sub` | 403 `NOT_ASSIGNED` |
| R8 | `decision.make` | `amount <= employee.approval_limit`, иначе только эскалация | 403 `APPROVAL_LIMIT_EXCEEDED` |
| R9 | `decision.override`, решение по эскалации | Решает не тот, кто вёл заявку и эскалировал её (`sub ≠ resource.assigned_to`) | 403 `FOUR_EYES` |
| R10 | `decision.override` | Только `bank_head`, `reason` обязателен | 403 `REASON_REQUIRED` |
| — | Конфликт интересов (сотрудник банка связан с заявителем) | Перенесено в «развитие»: у сотрудника нет членств, сопоставлять пришлось бы по ИНН физлица | — |

Атрибуты, которых требовала постановка: `company_id` используется в R1 и R5, статус заявки в R2, R4 и R6, назначенный сотрудник в R7 и R9, лимит суммы в R3 и R8.

Текст отказа человекочитаемый, например «Подать заявку на 5 000 000 ₽ может руководитель: ваш лимит 3 000 000 ₽». Это прямо работает на UX-критерий 03.

**Списки.** Функция `scope_filter(subject, "application")` возвращает SQL-предикат. Для клиента это `org_id = token.org`. Для аналитика: `status IN queue AND status ≠ draft AND (assigned_to = sub OR assigned_to IS NULL)`. Для head: всё, кроме `draft`. Для `bank_admin` выборка пустая.

**Р5. Чужой объект: 404 или 403.** Решение: объект чужой организации и черновик для банка дают 404. Отказ по правам или лимиту внутри своей организации даёт 403 `{code, message}`. Альтернатива: всегда 403. Почему: 404 не раскрывает, что объект существует, а 403 с кодом нужен для UX-подсказки.

### 5.5 Где и как проверяется

| Где | Что проверяет | Чем |
|---|---|---|
| Фронт | Ничего не решает, только показывает или скрывает кнопки по `/me` | — |
| BFF | Подпись и `exp`, чтобы вовремя сделать refresh. Права не решает | PyJWT + JWKS |
| Request | JWT, затем RBAC по роли, затем ABAC по заявке из своей БД, для списков `scope_filter` | `libs/authz` |
| Scoring | Пользовательские GET: `scoring.read_summary` / `read_details`. Обработчики событий прав пользователя не проверяют | `libs/authz` |
| Identity | Свои ручки: `org.members.manage`, `user.manage`, `audit.read` | `libs/authz` |

Правило для всех сервисов: `org_id`, `user_id` и `created_by` берутся **только из токена**, а не из тела запроса.

Обязательный тест в каждом сервисе: на каждую ручку с `{id}` запрос под чужой организацией должен вернуть 404.

**Р6. Где решать ABAC.** Решение: локально в каждом сервисе, claims плюс свои данные. Альтернатива: PDP-вызов `/authz/check` в Identity. Почему локально: схема запрещает прямой HTTP внутри периметра, атрибуты заявки лежат в Request, и Identity не становится единой точкой отказа. Batch `/authz/check` для подсказок UI — Could, сначала хватает `/me`. Если его сделаем, то с пометкой «не для enforcement».

**Р7. Что лежит в токене.** Решение: роли и атрибуты, а права вычисляются из `roles.yaml`. Альтернатива: `perms[]` в токене. Почему: один источник правды, токен меньше. Эффективные права для UI отдаёт `/me`.

---

## 6. Токены и сессии

**Access JWT**: RS256, `kid` в заголовке, в payload нет ПДн.

```json
{
  "iss": "identity", "aud": ["bff", "request", "scoring"],
  "sub": "<user uuid>", "sid": "<session uuid>", "kind": "client",
  "org": "<active org uuid>", "roles": ["org_finance"],
  "attrs": {"can_sign": false, "amount_limit": 3000000, "valid_until": null},
  "av": 7, "amr": ["pwd"], "auth_time": 1792000000,
  "iat": 0, "exp": 0, "jti": "<uuid>"
}
```

У сотрудника банка `org = null`, `roles` вида `["bank_analyst"]`, `attrs = {"approval_limit": 3000000}`.

| Параметр | Значение |
|---|---|
| TTL access | 10 мин |
| TTL refresh | 7 дней для клиента, 12 ч для сотрудника. Новый токен при каждом обновлении |
| Окно step-up | 5 мин (`amr` плюс `reauth`, новый `auth_time`) |
| Допуск на расхождение часов | 30 с |
| Кэш JWKS у потребителей | 10 мин, перезапрос при неизвестном `kid` |

**Refresh.** Формат `<sid>.<random 256 бит>`, в БД хранится SHA-256. Если `sid` валиден, а хэш не совпал ни с текущим, ни с `prev_refresh_hash` в окне 20 с, это повторное использование: сессия отзывается. Окно 20 с нужно, чтобы параллельные запросы из BFF не разлогинивали пользователя.

**Refresh всегда пересобирает claims из БД**: членство, роль, атрибуты, `av`. Если членство отозвано, выдаётся токен с `org = null`. Если учётка заблокирована, ответ 401 и отзыв сессии. `switch-org` проверяет, что членство активно.

**Отзыв до истечения TTL.** Блокировка, смена роли или атрибутов, отзыв членства увеличивают `users.authz_version` и публикуют `identity.user.authz_changed {user_id, av}`. Request и Scoring держат в памяти отображение `user_id → min_av` и на токен со старым `av` отвечают 401. BFF делает refresh и получает новые claims.

Ограничения, которые прописываем в README: карта в памяти теряется при рестарте сервиса (окно до 10 мин), после `logout` access живёт до 10 мин.

**Ключи.** Если `ENV=local` и ключа нет, entrypoint генерирует RSA-2048 в именованный volume. На стенде ключ берётся из GitHub Secrets и записывается в `.env` на VPS. Каталоги `keys/` и `.env` в `.gitignore`. Ротация ключей не делается: в JWKS один `kid`.

**Р8. Как раздавать публичный ключ.** Решение: `GET /.well-known/jwks.json`, единственное задокументированное исключение из правила «внутри периметра только брокер» (инфраструктурный вызов, не бизнес-логика). Альтернатива: монтировать публичный ключ в контейнеры через общий volume или env, тогда HTTP нет совсем. Почему JWKS: это стандарт, и на нём держится аргумент для README «в банке Identity заменяется на Keycloak или корпоративный IdP без изменений в сервисах» (критерий 06).

**Р9. Отзыв прав.** Решение: `authz_version` и событие. Альтернативы: denylist по `sid` (не покрывает смену прав без logout) или introspect в Identity на критичных действиях (синхронный HTTP против схемы). Запасной вариант при нехватке времени: только короткий TTL.

**Р10. Токены в браузере.** Решение: httpOnly-cookie у BFF (паттерн token handler). Альтернатива: JWT во фронте в памяти или `localStorage`. Почему cookie: защита от кражи токена через XSS, это пункт критерия 05.

Флаги cookie: `HttpOnly`, `SameSite=Lax`, `Secure` из env (`COOKIE_SECURE=false` локально), у refresh `Path=/api/auth`. CSRF закрываем заголовком `X-Requested-With` на мутациях. Фронт и BFF стоят за одним nginx на одном origin, поэтому CORS не нужен.

---

## 7. API

Сервис Identity, префикс `/v1`. Наружу торчит только через BFF и nginx (`/api/auth/*`, `/api/identity/*`). Все ручки описаны в OpenAPI с примерами в схемах, плюс коллекция Bruno в `docs/api/`.

| Метод | Путь | Кто вызывает | Назначение | MoSCoW |
|---|---|---|---|---|
| POST | `/v1/auth/login` | BFF | Логин и пароль → access, refresh. Блокировка после неудачных попыток | M |
| POST | `/v1/auth/refresh` | BFF | Ротация, пересборка claims, обнаружение повторного использования | M |
| POST | `/v1/auth/logout` | BFF | Отзыв сессии | M |
| POST | `/v1/auth/switch-org` | BFF | Новый access с другим `org` после проверки членства | M |
| GET | `/v1/me` | BFF | Учётка, профиль, членства, эффективные права и атрибуты в активной организации | M |
| GET | `/v1/organizations/{id}` | BFF | Карточка компании (R1) | M |
| GET | `/v1/demo-accounts` | BFF | Список кнопок «Войти как…», только при `DEMO_MODE=true` | M |
| GET | `/.well-known/jwks.json` | BFF, Request, Scoring | Публичные ключи | M |
| GET | `/healthz`, `/readyz` | compose | Liveness. Readiness проверяет БД; если брокер упал, сервис degraded, но ready | M |
| GET | `/v1/organizations/{id}/members` | BFF | Участники и их полномочия | S |
| GET | `/v1/roles` | BFF | Матрица ролей для экрана «Доступы» | S |
| GET | `/v1/admin/audit?actor=&action=&org=&from=&to=` | BFF (`audit.read`) | Журнал аудита Identity | S |
| POST | `/v1/auth/register` | BFF | Регистрация клиента: логин, пароль, ФИО, согласие на ПДн. Без подтверждения почты | S |
| POST | `/v1/organizations` | BFF | Привязка по ИНН: `ext-mocks` → организация в статусе `unverified`, пользователь становится `org_admin` без `can_sign`. Если у организации уже есть участники, 409 «обратитесь к администратору компании» | S |
| POST | `/v1/organizations/{id}/verify` | BFF | Симуляция «Подтвердить полномочия через Госуслуги Бизнес» → `verified`, `can_sign=true`, `basis=gosuslugi_sim` | S |
| POST | `/v1/auth/step-up` | BFF | Повторный ввод пароля → access с `amr: reauth` (симуляция ПЭП) | S |
| PATCH | `/v1/me/profile` | BFF | ФИО, телефон, должность | S |
| POST, PATCH, DELETE | `/v1/organizations/{id}/members[/{user_id}]` | BFF (`org.members.manage`) | Добавить зарегистрированную учётку по логину, изменить роль и атрибуты, отозвать | C |
| POST | `/v1/admin/users/{id}/block`, `/unblock`, `/reset-password` | BFF (`user.manage`) | Блокировка; сброс пароля вместо восстановления по почте | C |
| POST | `/v1/authz/check` | BFF | Batch-подсказки для UI, не для enforcement | C |

Ручек `/internal/*`, `/oauth/token`, `/introspect` нет: внутри периметра сервисы общаются только через брокер.

**Р11. Онбординг компании.** Решение (Should): регистрация, затем привязка ИНН через мок ЕГРЮЛ, затем симуляция подтверждения полномочий. До подтверждения подать заявку нельзя (R5). Альтернативы: сразу владелец (захват чужой компании по ИНН), сверка ФИО или ИНН руководителя (публичные данные, тоже захват), только seed-учётки. Почему так: симуляция внутри продукта соответствует ограничениям кейса 04 и 06, а допущение честно описано в README. Если не успеваем, оставляем только seed.

**Р12. Добавление сотрудников компании.** Решение (Could): администратор добавляет уже зарегистрированную учётку по логину. Альтернатива: инвайт-код, который показывается в UI. Почему: в демо всё задаёт seed, а инвайты — это ещё таблица и лишний экран.

---

## 8. События в брокер

RabbitMQ, exchange `identity.events` (topic), клиент FastStream (AsyncAPI генерируется бесплатно). Публикация через outbox и фоновый relay. Потребители идемпотентны по `event_id`. Если брокер недоступен, outbox копит события, а вход продолжает работать.

Конверт: `event_id`, `type`, `version`, `occurred_at`, `producer: "identity"`, `correlation_id`, `actor_id`, `payload`.

**Identity публикует**

| Событие | Payload | Кто слушает и зачем |
|---|---|---|
| `identity.user.authz_changed` | `user_id`, `av` | Request, Scoring: инвалидировать старые токены |
| `identity.user.registered` / `updated` | `user_id`, `kind`, `full_name`, `position` | Request: проекция имён для карточек |
| `identity.user.blocked` / `unblocked` | `user_id`, `reason_code` | Request: снять назначения, приостановить черновики |
| `identity.organization.created` / `updated` / `verified` | `org_id`, `inn`, `name`, `legal_form`, `okved_main`, `region`, `registered_on`, `registry_status`, `verification` | Request (карточка заявителя), Scoring (ключ обогащения), лента |
| `identity.membership.granted` / `changed` / `revoked` | `user_id`, `org_id`, `role`, `can_sign`, `amount_limit`, `valid_until` | Request: подписанты, снятие «черновик в работе» |
| `identity.employee.changed` | `user_id`, `roles`, `approval_limit`, `active` | Request: очередь, назначение, эскалация |

**Identity слушает:** в MVP ничего. Could: `registry.organization.status_changed` от мока. Если компания ликвидирована, ставим `registry_status=liquidated`, и R5 блокирует новые заявки.

Аудит в брокер не отправляем: пишем синхронно в свою таблицу, чтобы не потерять.

**Р13. ПДн в событиях.** Решение: в JWT и логах ПДн нет, в событиях `user.*` есть только ФИО и должность, это минимум для проекции Request. Альтернатива: в событиях только UUID, а имена BFF дотягивает из Identity по HTTP при сборке экрана. Почему ФИО в событии: иначе Request показывает менеджеру UUID вместо имени, либо нужен HTTP внутри периметра. Исключение фиксируем в README (152-ФЗ, минимизация).

---

## 9. Безопасность

### Обязательно (не режем)

| Мера | Деталь |
|---|---|
| Хэш паролей | argon2id (`argon2-cffi`), `check_needs_rehash` при входе. Пароль от 10 до 128 символов |
| Перебор логинов | Для несуществующего логина всё равно считается фиктивный хэш. Ошибка одна: «Неверный логин или пароль» |
| Брутфорс | 5 неудач на пару «учётка + IP» → блокировка на 5 мин. `limit_req` в nginx на `/api/auth/` (nginx уже есть в compose). Реальный IP берётся через `uvicorn --proxy-headers --forwarded-allow-ips=<nginx>`, чужому `X-Forwarded-For` не доверяем |
| JWT | RS256, проверяются `iss`, `aud`, `exp`. Ключ не в git |
| Refresh | Ротация, обнаружение повторного использования, пересборка claims |
| Cookie | HttpOnly, SameSite=Lax, Secure из env, CSRF-заголовок |
| Изоляция | R1 с 404, `scope_filter`, id только из токена, тест на каждую ручку с `{id}` |
| ПДн | Нет в JWT и логах. structlog в JSON с маскированием email, телефонов, паролей и токенов, `request_id` сквозной |
| Аудит | `login`, `login_failed`, `locked`, `logout`, `refresh_reuse`, `membership.*`, `org.verified`, `user.blocked`, `deny`. У роли БД нет прав на `UPDATE` и `DELETE` |
| Демо-учётки на стенде | `is_demo=true`: смена пароля и блокировка запрещены. Исключения: `lockout@`, `blocked@`. Ночной reseed на VPS по cron |
| Секреты | Только env через `pydantic-settings`. В `.env.example` безопасные dev-значения |
| Валидация | pydantic на входе, только ORM и параметризованные запросы |

### Сознательно отложено

| Что | Почему это нормально |
|---|---|
| Восстановление пароля, подтверждение почты, СМС-коды | Кейс запрещает почту и СМС (огр. 05). Замена: сброс пароля админом банка (Could), step-up паролем |
| Реальные ЕСИА, МЧД, УКЭП | Не подключить в рамках хакатона. Симуляция в продукте, описана как допущение |
| client_credentials, mTLS, introspect | Внутри периметра нет HTTP между сервисами |
| Ротация ключей, OIDC discovery, список сессий, `logout-all` | Для демо ценность около нуля. Описываем как путь развития |
| Цепочка хэшей в аудите | При параллельных вставках `prev_hash` нужно сериализовать, а эксперт это не проверит. Хватает запрета UPDATE и DELETE |
| slowapi | Дублирует `limit_req` в nginx |
| Хранение denylist и `min_av` вне памяти | Окно уязвимости ограничено TTL 10 мин. Описываем в README |
| Keycloak | Тяжёлый для ПК эксперта, а членства в компаниях и ABAC всё равно писать самим. В README: «заменяется на корпоративный IdP с тем же контрактом JWKS» |
| Конфликт интересов | Требует сопоставления по ИНН физлица, это развитие |

---

## 10. Seed и тестовые учётки

- Справочник ролей и прав живёт в `roles.yaml`. Демо-данные загружает идемпотентный `python -m identity.seed` в entrypoint после `alembic upgrade head`. Эксперту нужен только `docker compose up`.
- Каталог `backend/seed/` общий для Identity, Request и `ext-mocks`. В нём `demo_ids.yaml` с фиксированными UUID и `companies.yaml` с ИНН и данными реестров.
- ИНН и ОГРН синтетические, с корректной контрольной суммой и кодом региона `00`, поэтому совпадение с реальной компанией невозможно. Названия с пометкой «-Демо». ФИО генерирует `Faker('ru_RU')` с фиксированным seed.
- Пароль у всех `Demo-2026!` из env `DEMO_PASSWORD`. Указан в README с пометкой «только синтетические учётки».
- На странице входа при `DEMO_MODE=true` есть кнопки «Войти как…».

**Р14. Домен логинов.** Решение: `*.example.com` (зарезервирован RFC 2606, email-validator его принимает). Перед написанием seed проверяем это тестом. Альтернатива: логин как строка со своей регуляркой, не email. Почему: `.test`, `.local` и домены без точки `EmailStr` отклоняет, а это предлагали все три черновика.

| Логин | Роль и компания | Что показывает в демо |
|---|---|---|
| `petrova@client.example.com` | ИП Петрова А. С., `org_admin`, `can_sign` | Сквозной путь за 5 минут: заявка → подпись → оферта |
| `ivanov@client.example.com` | `org_admin` и `can_sign` в ООО «Пекарня Колосок-Демо» и ООО «СтройМастер-Демо» | Переключение компании; заявка другой компании даёт 404 |
| `smirnova@client.example.com` | `org_finance` в «Колоске», лимит 3 млн, без `can_sign` | 3 млн подаётся, 5 млн даёт `AMOUNT_LIMIT_EXCEEDED`, принять оферту нельзя (`SIGN_RIGHT_REQUIRED`) |
| `kozlov@client.example.com` | `org_operator` в «Колоске» | Готовит черновик и документы, кнопки «Подать» нет |
| `vector@client.example.com` | `org_admin` ООО «Вектор-Демо», `registry_status=liquidated` | R5: заявку не подать, `ORG_INACTIVE` |
| `new@client.example.com` | Без компании | Онбординг: ИНН «Новый Клиент-Демо» (есть только в моке) → автозаполнение → симуляция Госуслуг |
| `lockout@client.example.com` | Клиент, блокировка разрешена | 5 неверных паролей → блокировка, запись в аудите |
| `blocked@client.example.com` | `status=blocked` | Отказ во входе, запись в аудите |
| `analyst1@bank.example.com` | `bank_analyst`, лимит 3 млн | Берёт заявку, запрашивает документы, одобряет в пределах лимита, эскалирует 10 млн |
| `analyst2@bank.example.com` | `bank_analyst`, лимит 3 млн | Чужая назначенная заявка даёт `NOT_ASSIGNED` |
| `head@bank.example.com` | `bank_head`, лимит 20 млн | Решение по эскалации, override с причиной, «четыре глаза» |
| `admin@bank.example.com` | `bank_admin` | Журнал аудита, блокировка `blocked@` и новых учёток, заявок не видит |

Блок «Что показать экспертам» в README:
1. `curl /.well-known/jwks.json`.
2. Блокировка `lockout@`.
3. `smirnova@` упирается в лимит и получает понятный 403.
4. `ivanov@` видит заявку другой компании как 404.
5. `analyst1@` не может одобрить 10 млн.
6. Повторное использование refresh отзывает сессию.

---

## 11. Стек

Все библиотеки открытые. Версии ниже — ориентиры, точные фиксируются в `uv.lock`, Python 3.12 в `.python-version`.

| Библиотека | Версия-ориентир | Зачем | Лицензия |
|---|---|---|---|
| fastapi, uvicorn[standard] | ≥0.115, ≥0.32 | API | MIT, BSD |
| pydantic, pydantic-settings, email-validator | 2.x, 2.x, ≥2.2 | Схемы, конфиг, `EmailStr` | MIT, Unlicense |
| SQLAlchemy[asyncio], asyncpg | 2.0.x, ≥0.30 | ORM, драйвер | MIT, Apache-2.0 |
| alembic | ≥1.14 | Миграции | MIT |
| argon2-cffi | ≥23.1 | Хэши паролей. **Не passlib**: не поддерживается и ломается на bcrypt ≥4.1 | MIT |
| PyJWT[crypto], cryptography | ≥2.10, ≥44 | RS256, `PyJWKClient`. **Не python-jose**: заброшен, были CVE | MIT, Apache/BSD |
| faststream[rabbit] | ≥0.5 | Брокер, AsyncAPI | Apache-2.0 |
| httpx | ≥0.28 | Вызов `ext-mocks`, тесты | BSD |
| structlog | ≥24 | JSON-логи, маскирование | MIT/Apache |
| PyYAML | 6.0.x | `roles.yaml`, seed | MIT |
| Faker | ≥30 | Синтетика | MIT |
| pytest, pytest-asyncio, ruff | 8.x, ≥0.24, свежий | Тесты, линтер | MIT, Apache |
| Postgres, RabbitMQ | 16, 3.13 (теги образов без `latest`) | Инфраструктура | PostgreSQL, MPL-2.0 |

Если понадобится хранилище типа Redis, берём Valkey (BSD). Формулировку «Redis не открытый» не используем: Redis 8 вышел под AGPLv3.

Структура:

```
backend/
  libs/authz/        roles.yaml, rules.py, scope.py, principal.py, verifier.py, statuses.py, tests/
  services/identity/ app/{api,domain,infra}, seed.py, alembic/
  seed/              demo_ids.yaml, companies.yaml
  uv.lock
```

Enum статусов заявки лежит в `libs/authz/statuses.py`. Request его импортирует, а не дублирует.

---

## 12. План по шагам

| # | Шаг | Ч | MoSCoW | Когда | Кто |
|---|---|---|---|---|---|
| 0 | **Контракт** в `docs/identity.md`: claims, `roles.yaml`, коды отказов, статусы заявки (вместе с Request), конверт событий, `demo_ids.yaml`, dev-фикстуры токенов | 2 | M | 21.10 | Identity |
| 1 | Каркас: uv, settings, Dockerfile, compose, Alembic, модели и миграция, `/healthz`, `/readyz` | 3 | M | 21–22.10 | Identity |
| 2 | Auth: login, argon2, RS256 с генерацией ключа, JWKS, refresh (ротация, повторное использование, пересборка), logout, `switch-org`, блокировка, proxy-headers | 4 | M | 22.10 | Identity |
| 3 | `libs/authz`: verifier, `Principal`, `require`, `authorize`, `scope_filter`, R1–R10, табличные тесты матрицы | 4 | M | 22.10, параллельно с шагом 2 | Второй человек (владелец Request) |
| 4 | Seed, `/demo-accounts`, `is_demo`, кнопки «Войти как…» (вместе с фронтом) | 2 | M | 22.10 | Identity |
| 5 | `/me` с эффективными правами, `GET /organizations/{id}` | 1 | M | 23.10 | Identity |
| 6 | `audit_log` (запись, права БД), `GET /admin/audit` | 1,5 | M (запись) / S (чтение) | 23.10 | Identity |
| 7 | Outbox, relay, события, `authz_version` и слушатель в `libs/authz` | 3 | S | 23.10 | Identity |
| 8 | Регистрация, привязка ИНН, симуляция Госуслуг | 3 | S | 24.10 | Identity |
| 9 | Step-up | 1,5 | S | 24.10 | Identity |
| 10 | Участники компании, админ: блокировка и сброс пароля, `/authz/check` | 2–3 | C | При наличии времени | Identity |
| 11 | Документация: примеры в OpenAPI, Bruno, таблица ролей и учёток в README, `docs/decisions.md`, раздел «Безопасность», проверка на чистой машине | 2 | M | 24–25.10 | Identity |

**Итого у разработчика Identity:** Must около 15,5 ч, Should около 7,5 ч, Must и Should вместе около 23 ч. Плюс 4 ч `libs/authz` у второго человека. Приоритет: 0 → 2 → 3 → 4, остальное после того, как работает сквозной сценарий.

**MoSCoW**

| Must | Should | Could | Won't (в README как развитие) |
|---|---|---|---|
| Вход и токены, `libs/authz` с R1–R8 и `scope_filter`, 404 и 403 с кодом, seed и кнопки «Войти как…», `is_demo`, `/me`, запись аудита, блокировка, документация | События и `authz_version`, онбординг по ИНН с симуляцией, step-up, R9–R10, чтение аудита, `/roles` | Управление участниками, админка, сброс пароля, batch `/authz/check`, событие от реестра | Ротация ключей, client_credentials, конфликт интересов, инвайты, Keycloak |

**Что режем при нехватке времени (сверху вниз):**
1. Всё из Could.
2. Онбординг: только seed-учётки, все организации `verified`.
3. Step-up: подпись одной кнопкой.
4. `authz_version`: остаётся только TTL 10 мин.
5. Outbox: публикация сразу после commit без гарантии доставки (так и пишем в README).
6. События, кроме `organization.*` и `user.registered`.

**Не режем никогда:** argon2, RS256 + JWKS, refresh с ротацией, R1 и `scope_filter`, R3 и R8 (главные демо-моменты), seed и кнопки «Войти как…», `is_demo`, аудит входов, таблицу учёток в README.

---

## 13. Риски и открытые вопросы

### Риски

| Риск | Мера |
|---|---|
| Identity съедает время кредитного пути | Потолок около 23 ч, контракт и dev-токены 21.10, Request не ждёт готовый Identity |
| IDOR: хендлер забыл вызвать `authorize` или `scope_filter` | Общий тест на 404 для каждой ручки с `{id}` и каждого списка |
| Статусы заявки разойдутся с правилами | Enum в `libs/authz`, Request его импортирует |
| Общая библиотека ломает три сервиса сразу | Тесты матрицы в CI, изменения только через PR с ревью |
| Эксперт опечатался и заблокировал демо-учётку | Блокировка по паре «учётка + IP» на 5 мин; для показа отдельная `lockout@` |
| Кто-то на публичном стенде испортил демо-учётки | `is_demo`, ночной reseed |
| Ключ пересоздаётся при рестарте | Именованный volume |
| `Secure`-cookie на `http://localhost` | `COOKIE_SECURE=false` по умолчанию |
| `EmailStr` отклонит демо-логины | Домен `example.com`, проверка тестом до seed |
| У эксперта не поднимается | `docker compose up` без ручных шагов, проверка на чистой машине 25.10 |

### Вопросы к лиду

| # | Вопрос | Предложение |
|---|---|---|
| В1 | Identity — отдельный контейнер или модуль общего бэкенда (Р1)? В `case.md` один `backend/Dockerfile` | Отдельный, по `architecture.md` |
| В2 | Допустим ли JWKS по HTTP как исключение из правила «только брокер» (Р8)? | Да, это инфраструктура |
| В3 | Будет ли в UI сотрудника отдельный экран назначения, то есть нужен ли `bank_manager` (Р4)? | Нет, назначает `bank_head` |
| В4 | Финальный список статусов заявки и кто их меняет | Черновик: `draft`, `submitted`, `info_requested`, `scoring`, `under_review`, `offer`, `counter_offer`, `rejected`, `accepted`, `signing`, `signed`, `withdrawn` |
| В5 | `amount_limit` клиента ограничивает только подачу или ещё и принятие оферты? | Только подачу |
| В6 | ФИО в событиях — исключение из правила «без ПДн» (Р13)? | Да, с записью в README |
| В7 | Кто владеет `ext-mocks` и формат `GET /egrul/{inn}`? Дописать Identity в вопрос 4 `architecture.md` | Владелец Scoring |
| В8 | Онбординг по ИНН с симуляцией Госуслуг в демо или только seed (Р11)? | Should, 3 ч |
| В9 | Step-up перед подписью нужен? | Should, 1,5 ч |
| В10 | Кто пишет `libs/authz` параллельно с Auth? | Владелец Request: он главный потребитель |
| В11 | Ночной reseed на стенде по cron допустим? | Да |
| В12 | Брокер RabbitMQ и FastStream: подтверждаем? Кто поднимает его в compose? | Да, по `architecture.md`, вопрос 7 |