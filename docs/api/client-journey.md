# Клиентский путь: ручки API и контракт для фронта

Путь взят из верхней части общей схемы (BPMN): пул «Пользак», пул «Банк», внутри банка — «Запросы» и «Сервис скоринга» («Модель оценки PD» → «Стратегия решения»).
Ручки — из [`openapi.json`](openapi.json). Он совпадает с кодом `develop` на 22.10.2026: `uv run python -m scripts.export_openapi --check` из `backend/`.
Полные схемы DTO — там же или в Swagger `/docs` запущенного бэка. Здесь — поля, которые нужны экранам.

Статусы в таблицах:
- ✅ есть и совпадает со схемой;
- 🟡 есть, но расходится со схемой;
- ❌ нет, план — в разделе 4.

---

## 1. Общие правила

| Что | Как |
|---|---|
| Пути | Бэк без префикса. Фронт ходит в `/api/*` (`VITE_API_BASE_URL`), vite-прокси срезает префикс: `/api/auth/login` → `/auth/login` |
| Авторизация | `Authorization: Bearer <access_token>` из `POST /auth/login` или `POST /auth/demo-login`. `expires_in` — в секундах. Refresh-ручки нет: на 401 — снова вход |
| Без токена | `GET /products`, `GET /products/{code}`, `POST /products/recommend`, `POST /products/{code}/calculate`, `POST /auth/login`, `POST /auth/demo-login`, `GET /auth/demo-accounts`, `GET /health`, `GET /ready` |
| Ошибки | `{code, message, details?}`: 401 `unauthorized`, 403 `permission_denied`, 404 `not_found`, 409 `conflict` / `invalid_transition`, 422 `validation_error`, 503 `unavailable`. Уточнение — в `details.code`, нарушения полей — в `details.violations: [{code, field}]` |
| Ошибка формы запроса | 422 от FastAPI: `{detail: [{loc, msg, type}]}` — другой формат, `http.ts` уже разбирает оба |
| Чужое | Чужая компания или заявка — **404**, не 403. Нет права внутри своей компании — 403, `details.code = org_permission_required`, `details.permission` |
| Деньги | В ответах — десятичная строка (`"1500000.50"`), на входе — число или строка, не больше 2 знаков |
| Ставки | Проценты годовых строкой: `"23.50"` — это 23,5% |
| Даты | ISO 8601: `date` — `2026-10-22`, `date-time` — с часовым поясом |
| Списки | `limit` / `offset`. BFF-списки отдают `{items, total}` |
| Черновик заявки | Оптимистичная блокировка: `PATCH` несёт `version`; устаревшая версия — 409, `details.code = version_conflict`, актуальная — в `details.version` |
| Кнопки | В заявке есть `available_actions` (что можно сделать сейчас с учётом прав) и `my_permissions`. Кнопки рисуем по ним, а не по статусу |
| Живые обновления | SSE: `POST /feed/stream-ticket` → `GET /feed/stream?ticket=…`. Билет нужен, потому что `EventSource` не умеет слать `Authorization`. Догонка — `last_event_id` или заголовок `Last-Event-ID` |

---

## 2. Путь по схеме → ручки

| # | Шаг на схеме | Кто | Ручки | Статус |
|---|---|---|---|---|
| 1 | Клиент на сайте → кредитный калькулятор | клиент, без входа | `GET /products`, `POST /products/recommend`, `POST /products/{code}/calculate` | ✅ |
| 2 | Авторизован? → вход в ЛК | клиент | `GET /me` (401 — на вход), `GET /auth/demo-accounts`, `POST /auth/demo-login`, `POST /auth/login` | ✅ |
| 3 | Есть ли бизнес? | банк | `GET /bff/dashboard`: `organizations`, `onboarding` | 🟡 ветки «нет (стартап)» нет — [4.6](#46-ветка-стартапа) |
| 4 | Подтянули данные из базы банка | банк | `GET /organizations/{id}`, `GET /organizations/{id}/financial-reports` | ✅ |
| 5 | Сверили данные с ЕГРЮЛ → данные изменились → подкачали новые | банк | `POST /organizations/{id}/verification`, результат — в `OrganizationRead.verification` | ✅ бэк сверяет и сам — по выписке из каждой заявки, [4.2](#42-сверка-с-егрюл) |
| 6 | Предскоринг (для каждого бизнеса) → «Предварительно подобранное предложение» | банк → клиент | `GET /organizations/{id}/pre-approved-offers`, `Dashboard.pre_approved`, `Dashboard.counters` | ✅ пересчёт по событиям clients (отчёт подан, компания проверена); ночного пакета нет |
| 7 | Клиент выбирает условия: сумма, срок, платёж — «калькулятор с учётом предскоринга» | клиент | `POST /bff/products/{code}/calculate`, `GET /bff/products/recommend`, `POST /products/recommend/{organization_id}`, `GET /products/{code}/eligibility` | ✅ график по ставке предодобрения; сверх предодобренного — причина и подсказка, не ошибка — [3.4](#34-выбор-условий-шаг-7) |
| 8 | Согласие: БКИ физлица + ПДн | клиент | `GET/POST /me/consents`, `DELETE /me/consents/{type}` — личные согласия; `PATCH /applications/{id}` → `consents` — согласия компании в заявке; `ClientApplicationCard.consents.head_credit_bureau`, `Dashboard.todo` → `consent_required` | ✅ |
| 9 | Пользователь выбрал конкретные условия | клиент | `POST /applications`, `PATCH /applications/{id}`, `GET …/completeness`, документы, `POST …/submit` | ✅ |
| 10 | Запросы: ГИР БО, Контур, ФНС, БКИ ЮЛ, БКИ ФЛ | банк | без фронта (`enrichment`); результат — в `UnderwriterCard.enrichment` и в `degraded` | ✅ ЕГРЮЛ/ЕГРИП, ФНС с блокировками счетов, ГИР БО, Контур, БКИ компании и руководителя (с его согласия), выписки — [4.4](#44-источники-гир-бо-контур-бки-физлица) |
| 11 | Стоп-фактор? → отказано | банк | без фронта (`decision`, причины `STOP_*`); клиенту — `client_status = rejected` и `decision.client_explanation` | ✅ `policy_v2`: стоп-факторы ГИР БО, Контура, ФНС и БКИ руководителя — [4.4](#44-источники-гир-бо-контур-бки-физлица) |
| 12 | Модель оценки PD | банк | без фронта (`scoring`); андеррайтеру — `UnderwriterCard.scoring`: сегмент, PD, грейд A–J, коды причин | ✅ [4.7](#47-скоринг-и-стратегия-как-на-схеме) |
| 13 | Стратегия решения: approve / counteroffer / отказ / ручная | банк | без фронта (`decision`); клиенту — `offer` и `decision` в карточке; андеррайтеру — триггеры, матрица в `rule_trace`, лимиты с `binding`, `rate_breakdown` | ✅ [4.7](#47-скоринг-и-стратегия-как-на-схеме) |
| 14 | Ручная проверка | андеррайтер | `GET /bff/backoffice/queue`, `GET /bff/backoffice/applications/{id}`, `POST /tasks/{id}/claim`, `POST /tasks/{id}/complete` | ✅ |
| 15 | Решение клиенту | клиент | `GET /bff/applications/{id}`, `GET /feed` + SSE | ✅ |
| 16 | counteroffer — клиент подтверждает | клиент | `POST …/offer/accept`, `POST …/offer/decline` | ✅ |
| 17 | «Подпиши договор: одобрили, но нужна подпись» | клиент | `GET /applications/{id}/contract`, `POST /applications/{id}/sign` | ✅ договор перед подписью — [3.7](#37-решение-оффер-подпись-выдача-шаги-1518) |
| 18 | Кредит оформлен | клиент | `client_status = issued`, `ApplicationOut.disbursement` | ✅ выдачу делает процесс после подписи (мок АБС) |
| — | Стартап: личный скоринг учредителя → бизнес-план → проектная оценка | клиент, банк | — | ❌ — [4.6](#46-ветка-стартапа) |

Вопросы на схеме:

- **«А можно без эл. доверенности брать кредит?»** Подать заявку — да: хватает права `submit_application` (бухгалтер его имеет по умолчанию). Подписать — нет: `sign` есть только у руководителя по реестру и у участника с доверенностью со scope `sign`. Доверенность выдаёт руководитель: `POST /organizations/{id}/members/{account_id}/poa`. Без неё бухгалтер подаёт заявку, но на `sign` получает 403.
- **«А можно в ЕГРЮЛ отчётность посмотреть?»** В ЕГРЮЛ бухотчётности нет, она в ГИР БО. Банк запрашивает её при рассмотрении заявки: андеррайтер видит `enrichment.gir_bo` в карточке — [4.4](#44-источники-гир-бо-контур-бки-физлица). Клиенту в кабинете — по-прежнему заявленная им отчётность (`POST /organizations/{id}/financial-reports`) плюс выручка по ФНС.

---

## 3. Ручки по шагам

### 3.1. Калькулятор до входа (шаг 1)

**`GET /products?purpose=`** → `ProductRead[]`: активные продукты в порядке каталога.
Экрану нужны `code`, `name`, `short_description`, `purposes`, `amount_min` / `amount_max`, `term_min_months` / `term_max_months`, `rate_base` / `rate_max`, `repayment_options`, `collateral_kind`, `min_business_age_months`, `allowed_legal_forms`, `required_documents`.

`purpose`: `working_capital`, `cash_gap`, `equipment`, `vehicles`, `real_estate`, `contract_execution`, `refinancing`, `expansion`.

**`POST /products/recommend`** — подбор по потребности, без проверки компании.

```json
{ "purpose": "working_capital", "amount": 3000000, "term_months": 24 }
```

Ответ `RecommendationsRead`:

```json
{
  "purpose": "working_capital",
  "amount": "3000000",
  "term_months": 24,
  "organization_id": null,
  "cash_gap_expected": null,
  "items": [
    {
      "rank": 1,
      "status": "available",
      "eligible": null,
      "fits": true,
      "reasons": [],
      "adjustments": [],
      "repayment": "annuity",
      "amount": "3000000",
      "term_months": 24,
      "monthly_payment_from": "…",
      "monthly_payment_to": "…",
      "product": { "code": "UNSECURED", "…": "ProductRead" }
    }
  ]
}
```

`status`: `available` | `needs_adjustment` (в `adjustments` — что поменять) | `unavailable`.

**`POST /products/{code}/calculate`** — график платежей.

```json
{ "amount": 3000000, "term_months": 24, "rate": null, "repayment": "annuity" }
```

Без `rate` берётся базовая ставка продукта, без `repayment` — схема продукта по умолчанию. Сумма, срок или ставка вне рамок продукта — 422.

Ответ `PaymentScheduleRead`: `amount`, `term_months`, `rate`, `repayment`, `monthly_payment`, `total_interest`, `total_paid`, `payments: [{number, due_date, principal, interest, total, balance_after}]`.

### 3.2. Вход (шаг 2)

| Ручка | Тело | Ответ |
|---|---|---|
| `GET /auth/demo-accounts` | — | `[{login, phone, role, caption, full_name}]` — список для экрана выбора демо-пользователя |
| `POST /auth/demo-login` | `{login}` | `{access_token, token_type: "bearer", expires_in}` |
| `POST /auth/login` | `{login, password}` | то же |
| `GET /me` | — | `MeRead`: `id`, `email`, `phone`, `role {id, name}`, `profile {last_name, first_name, middle_name, position}`, `permissions[]`, `policies{}` |
| `PATCH /me/profile` | `{last_name?, first_name?, middle_name?, position?}` | `MeRead` |

### 3.3. Главная: компания и предодобрение (шаги 3–6)

**`GET /bff/dashboard?organization_id=`** — главный экран. Без `organization_id` берётся первая компания пользователя.

```text
Dashboard {
  onboarding: boolean            // true — у пользователя нет ни одной компании, остальное пусто
  organization: { id, name, inn, legal_form, my_role, my_permissions[], verification_status, registry_status } | null
  organizations: [{ id, name, inn, legal_form, my_role, my_permissions[] }]
  counters: { active_applications, action_required_count, pre_approved_max_amount, pre_approved_rate_from, last_activity_at } | null
  pre_approved: [{ product_code, product_name, max_amount, rate_from, term_max_months, valid_until }]
  active_applications: ApplicationRow[]
  todo: [{ application_id, number, kind: info_requested | offer_ready | signing | consent_required, title }]
  feed: { unread, items: FeedItem[] }
  news: [{ id, title, body, published_at, relevance[] }]
  degraded: string[]             // какие блоки не загрузились — показать заглушку, а не ошибку
}
```

`consent_required` получает только руководитель по реестру и только пока у компании есть заявка до решения (`submitted`, `in_review`, `info_requested`), а его действующего `credit_bureau_personal` нет. Пункт один на компанию, с номером последней такой заявки; согласие даётся через `POST /me/consents` ([4.3](#43-личные-согласия-пдн-и-бки-физлица)).

| Ручка | Что | Ответ |
|---|---|---|
| `GET /organizations` | мои компании | `[{id, name, inn, legal_form, registry_status, my_role, my_permissions}]` |
| `GET /organizations/{id}` | карточка: реквизиты, адрес, ОКВЭД, возраст бизнеса, руководитель по реестру, сверка | `OrganizationRead`, в нём `verification {status: unverified \| verified \| mismatch, checked_at, discrepancies: [{field, declared, registry}]}` |
| `POST /organizations/{id}/verification` | сверить с ЕГРЮЛ/ЕГРИП и подкачать изменения | `VerificationResultRead {organization, updated_fields, discrepancies}`, подробно — [4.2](#42-сверка-с-егрюл) |
| `GET /organizations/{id}/financial-reports` | отчётность | `[{id, period_year, period_quarter, source: declared \| fns \| bank_statement, revenue, expenses, net_profit, total_liabilities, monthly_debt_payments, submitted_by, submitted_at}]` |
| `POST /organizations/{id}/financial-reports` | подать отчёт | тело `{period_year, period_quarter?, revenue, expenses?, net_profit?, total_liabilities?, monthly_debt_payments?}` → 201 новый / 200 уточнён. Запускает пересчёт предодобрения |
| `GET /organizations/{id}/pre-approved-offers` | предодобрение | `[{product_code, max_amount, rate_from, term_max_months, valid_until, basis: estimate \| full, note}]` |

Предодобрение действует 30 дней. Пересчёт перезаписывает все предложения компании: продукт, который больше не подходит, пропадает. Оценка консервативная, без БКИ и выписок.

### 3.4. Выбор условий (шаг 7)

**`GET /bff/products/recommend?purpose=&amount=&term_months=&organization_id=`** (нужен вход) → `Recommendations`:

```text
{
  items: [{
    product_code, product_name, short_description, rank, fit,
    eligible: boolean | null,                         // null — без organization_id
    eligibility: [{ code, passed, message }],
    rate_from, amount_max, term_max_months,
    payment_from: string | null,
    pre_approved_max: string | null                   // предодобренный максимум по этому продукту
  }],
  degraded: string[]
}
```

**`POST /bff/products/{code}/calculate?organization_id=`** (нужен вход и `credits.read`) — калькулятор с учётом предодобрения. Тело — как у `POST /products/{code}/calculate`, но без `rate`: ставку определяет бэк, `rate` в теле — 422. Без `repayment` — схема продукта по умолчанию.

```json
{ "amount": 5000000, "term_months": 24, "repayment": "annuity" }
```

Ответ `PersonalSchedule`:

```text
{
  schedule: { amount, term_months, rate, repayment, monthly_payment, total_interest, total_paid, payments[] },
                                        // как PaymentScheduleRead (3.1); ставка — rate_from предодобрения, без него — rate_base продукта
  pre_approved: { max_amount, rate_from, term_max_months, valid_until, basis: estimate | full } | null,
  within_pre_approved: boolean | null,  // null — по этому продукту ничего не предодобрено
  eligible: boolean,
  reasons: [{ code, passed, message }], // причины eligibility + amount_above_pre_approved / term_above_pre_approved
  suggestion: { amount, term_months, monthly_payment } | null,  // запрос, урезанный до предодобренного
  degraded: string[]                    // ["pre_approved"] — decision не ответил, считаем без предодобрения
}
```

| Случай | Ответ |
|---|---|
| Предодобрения по продукту нет | `pre_approved: null`, `within_pre_approved: null`, ставка — `rate_base`, `suggestion: null` |
| Запрос в рамках предодобрения | `within_pre_approved: true`, ставка — `rate_from`, `suggestion: null` |
| Сумма больше `max_amount` | `within_pre_approved: false`, причина `amount_above_pre_approved` («Предварительно доступно до 4 000 000 ₽»); график — по запрошенной сумме, `suggestion` — по `max_amount` |
| Срок больше `term_max_months` | `within_pre_approved: false`, причина `term_above_pre_approved`; в `suggestion` срок урезан до `term_max_months` |
| Компания не проходит eligibility | `eligible: false`, причины — из eligibility; график всё равно считается |
| `decision` не ответил | как без предодобрения, `degraded: ["pre_approved"]` |
| Сумма, срок или схема вне рамок продукта | 422, как у `POST /products/{code}/calculate`: `details.field` — `amount`, `term_months` или `repayment`; `details.code` — `out_of_range` (с `min` и `max`) или `not_offered` (с `options`) |
| Продукта нет / продукт в архиве | 404 / 409 `product_not_available` |
| Чужая компания | 404 |

Подачу сверх предодобренного бэк не блокирует: окончательное решение — после проверки, банк может ответить counteroffer. Фронт показывает причины из `reasons` и предлагает `suggestion`, кнопку подачи не прячет. Если урезанная сумма или срок меньше минимума продукта, `suggestion: null`.

| Ручка | Что |
|---|---|
| `POST /products/recommend/{organization_id}` | то же в терминах модуля products: `RecommendationsRead` с причинами и `cash_gap_expected` (ожидается кассовый разрыв) |
| `GET /products/{code}/eligibility?organization_id=` | `{product_code, organization_id, eligible, reasons: [{code, passed, message}]}` |
| `POST /products/{code}/calculate` | график без компании, см. 3.1. Предодобрение не учитывает: для компании — `POST /bff/products/{code}/calculate` выше |

### 3.5. Заявка: черновик → подача (шаги 8–9)

1. **`POST /applications`** `{organization_id, product_code}` → 201 `ApplicationOut`, `status = draft`, `version = 1`. Рамки продукта фиксируются в `product_terms`: это снимок версии продукта на момент создания.
2. **`PATCH /applications/{id}`** — автосохранение, все блоки необязательны:

   ```json
   {
     "version": 1,
     "request": { "amount": 3000000, "term_months": 24, "purpose": "working_capital", "purpose_comment": null },
     "product_fields": {},
     "collateral": { "type": "real_estate", "description": "…", "declared_value": 50000000, "owner": "self" },
     "consents": { "personal_data": true, "credit_bureau": true }
   }
   ```

   `product_fields` сливается с сохранённым, `null` удаляет ключ. Схема полей — `product_terms.application_fields_schema`. Ответ — `ApplicationOut` с `version + 1`.
3. **`GET /applications/{id}/completeness`** → `{complete, violations: [{code, field}]}`. Пример нарушения: `{"code": "missing", "field": "consents.credit_bureau"}`. Для документов `field` — `documents.<type>`.
4. Документы (типы — `product_terms.required_documents[].type`):
   - `POST /applications/{id}/documents` `{type, filename, content_type, size_bytes}` → 201 `{document (status pending_upload), upload: {url, method, headers, expires_at}}`;
   - браузер грузит файл сам по `upload.url` с `upload.method` и `upload.headers` (MinIO через nginx `/credit-documents/`, до 25 МБ);
   - `POST /applications/{id}/documents/{document_id}/confirm` → `DocumentOut` (status `uploaded`);
   - `GET …/documents/{document_id}/download` → `{url}`; `DELETE …/documents/{document_id}` → 204.
5. **Личные согласия руководителя** — не в заявке, а на аккаунте: `POST /me/consents {"types": ["personal_data", "credit_bureau_personal"]}` ([4.3](#43-личные-согласия-пдн-и-бки-физлица)). Без `credit_bureau_personal` руководителя по реестру банк не запрашивает его кредитную историю; подать заявку это не мешает.
6. **`POST /applications/{id}/submit`** → `ApplicationOut`, `status = submitted`. Неполная заявка — 422 с `details.violations` (тот же формат, что у completeness). При подаче фиксируется снимок компании: поле `organization` в ответе.

### 3.6. Пока банк думает (шаги 10–15 глазами клиента)

**`GET /bff/applications/{id}`** → `ClientApplicationCard`:

```text
{
  id, number, organization: { id, name, inn },
  product: { code, name, amount_min, amount_max, term_min_months, term_max_months, rate_base, rate_max },
  status, client_status,
  client_stage: string | null,          // человеческое название этапа процесса, например «Оцениваем заявку»
  request, product_fields, collateral, documents[],
  info_request: { id, requested_fields[], requested_documents[], comment, created_at, due_at, status, answered_at } | null,
  offer: { kind: as_requested | counter, amount, term_months, rate, monthly_payment, schedule_type, conditions[], expires_at } | null,
  decision: { outcome, terms, alternative_product_code, client_explanation, improvement_hints[], requested_info } | null,
  consents: {
    head_credit_bureau: {               // null — в реестре нет руководителя или identity недоступен (тогда в degraded — head_consent)
      required: boolean,                // БКИ руководителя запрашивается для каждой заявки (policy_v2)
      given: boolean,                   // у руководителя есть действующее credit_bureau_personal
      given_at: date-time | null,
      head_name: string                 // ФИО по реестру; у руководителя может не быть аккаунта в компании — тогда given = false
    } | null
  },
  timeline: [{ at, kind, title }],
  feed: FeedItem[],
  available_actions[], my_permissions[],
  created_at, updated_at, submitted_at, closed_at,
  degraded[]
}
```

Статус бэка → `client_status` для экрана:

| `status` | `client_status` |
|---|---|
| `draft` | `draft` |
| `submitted` | `submitted` |
| `in_review` | `checking`; на этапах «Оцениваем…», «Подбираем…», «…у специалиста» — `scoring` |
| `info_requested` | `info_requested` |
| `offer_ready` | `approved` (`offer.kind = as_requested`) или `counter_offer` (`counter`) |
| `signing` | `signing` |
| `signed`, `disbursed` | `issued` |
| `rejected` | `rejected` |
| `offer_declined` | `declined` |
| `expired` | `expired` |
| `cancelled` | `cancelled` |

`available_actions` по статусам (в ответе остаются только те, на которые у пользователя есть право):

| Статус | Действия |
|---|---|
| `draft` | `edit`, `upload_document`, `submit`, `cancel` |
| `submitted` | `cancel` |
| `info_requested` | `upload_document`, `answer_info_request`, `cancel` |
| `offer_ready` | `accept_offer`, `decline_offer`, `cancel` |
| `signing` | `sign` |

Прочие ручки этого шага:

| Ручка | Что |
|---|---|
| `GET /bff/applications?organization_id=&status=&limit=&offset=` | `{items: ApplicationRow[], total}`. В строке есть `client_status`, `action_required`, `offer_amount`, `offer_rate` |
| `GET /feed?organization_id=&application_id=&unread_only=&limit=&offset=` | `{items: FeedItemRead[], total, limit, offset}` |
| `GET /feed/unread-count` | `{count}` |
| `POST /feed/{item_id}/read`, `POST /feed/read-all` | отметить прочитанным |
| `POST /feed/stream-ticket` | `{ticket, expires_at, expires_in, stream_url}` → `GET stream_url` через `EventSource` |
| `GET /news?organization_id=&limit=`, `POST /news/{news_id}/read` | персональные новости |

**Дозапрос** (банк вернул `REQUEST_INFO`, `client_status = info_requested`):
1. Загрузить документы из `info_request.requested_documents`. Документ сам привязывается к открытому дозапросу; тип, которого банк не просил, — 422 `unexpected_document`.
2. Поправить поля из `requested_fields` через `PATCH /applications/{id}`.
3. Отправить ответ: `POST /applications/{id}/info-requests/{info_request_id}/answer`, без тела. Заявка возвращается в `in_review`.

### 3.7. Решение, оффер, подпись, выдача (шаги 15–18)

| Ручка | Тело | Что происходит |
|---|---|---|
| `POST /applications/{id}/offer/accept` | — | `offer_ready` → `signing`. Нужно и для `as_requested`, и для `counter` |
| `POST /applications/{id}/offer/decline` | `{reason?}` или пусто | → `offer_declined` |
| `GET /applications/{id}/contract` | — | Договор для экрана подписи, с `signing` и дальше; раньше — 409 `contract_not_ready`. Право — чтение заявки. Ответ ниже |
| `POST /applications/{id}/sign` | `{password, offer_hash}` | Пароль аккаунта ещё раз (step-up), неверный — 422 `invalid_password`. `offer_hash` — из договора: если оффер изменился после открытия договора — 409 `offer_changed`, договор открыть заново. Нужно право `sign`. Ответ `{application, signature: {signed_at, offer_hash, edo_document_id, simulated}}` |
| `POST /applications/{id}/cancel` | `{reason?}` или пусто | Отмена в `draft`, `submitted`, `info_requested`, `offer_ready` |

Договор `ContractOut` рендерит фронт из полей, PDF нет:

```json
{
  "number": "2026-000123",
  "offer_hash": "9f2c…64 hex",
  "status": "unsigned",
  "borrower": { "name": "ООО «Ромашка»", "inn": "7701158817", "ogrn": "…", "kpp": "…", "legal_form": "ooo", "head_name": "Смирнова Анна Андреевна" },
  "signers": [{ "account_id": "…", "name": "Смирнова Анна Андреевна", "authority": "registry" }],
  "terms": { "kind": "as_requested", "amount": "3000000.00", "term_months": 24, "rate": "23.50", "monthly_payment": "…", "schedule_type": "annuity", "conditions": [], "expires_at": "…" },
  "schedule": { "amount": "3000000.00", "term_months": 24, "rate": "23.50", "repayment": "annuity", "monthly_payment": "…", "total_interest": "…", "total_paid": "…", "payments": [{ "number": 1, "due_date": null, "principal": "…", "interest": "…", "total": "…", "balance_after": "…" }] },
  "signature": null
}
```

- `number` — номер заявки, отдельной нумерации договоров нет.
- `signers` — кто вправе подписать сейчас: руководитель по реестру (`registry`) и участники с доверенностью со scope `sign` (`power_of_attorney`). Бухгалтер без доверенности сюда не попадает: ему договор виден, но подписать он не может.
- После подписи `status = signed`, `signature = {signed_by, signed_at, edo_document_id, simulated}`.

После подписи процесс сам выдаёт кредит через мок АБС: `status = disbursed`, в заявке `disbursement {reference, disbursed_at, simulated}`, у клиента `client_status = issued`. Оффер, не принятый до `offer.expires_at`, уходит в `expired`.

### 3.8. Банк: ручная проверка (шаг 14)

| Ручка | Что |
|---|---|
| `GET /bff/backoffice/queue?status=&sort=&limit=&offset=` | `{items: [{task_id, application_id, number, company_name, inn, product_code, amount, score, risk_grade, cash_gap, routing_reasons[], due_at, overdue, assignee_id, status, created_at}], total}` |
| `GET /bff/backoffice/applications/{id}` | `UnderwriterCard`: `application`, `client_status`, `enrichment` (что ответили источники), `scoring` (сегмент, скоркарта, балл, `pd_12m`, грейд A–J, факторы, `reason_codes`), `decision` (`rule_trace`, `limits` с `binding`, `reason_codes`, `triggers`, `rate_breakdown`), `product_fit`, `timeline`, `process`, `task`, `degraded` |
| `POST /tasks/{id}/claim` | взять задачу → `TaskOut` |
| `POST /tasks/{id}/complete` | `{decision: approve \| counter_offer \| reject \| request_info, amount?, term_months?, rate?, conditions[]?, requested_documents[]?, comment}` → `TaskOut` |
| `GET /tasks?role=&status=`, `GET /tasks/{id}` | задачи; деталь — вместе с процессом |
| `GET /processes/{application_id}`, `GET /workflows`, `GET /workflows/{code}/diagram` | процесс заявки и BPMN-схема для подсветки текущего шага |
| `GET /bff/backoffice/metrics?date_from=&date_to=` | метрики по дням и продуктам |

---

## 4. Чего не хватает: план

Реализация по модулям, порядок работ и диаграммы — в [roadmap.md](roadmap.md). Если контракты здесь и там расходятся, верен roadmap.

| # | Что | Шаг схемы | Изменение API | Приоритет | Модули |
|---|---|---|---|---|---|
| 4.1 | Калькулятор с учётом предскоринга — ✅ сделано | 7 | новая `POST /bff/products/{code}/calculate` | Should | bff |
| 4.2 | Сверка с ЕГРЮЛ — ✅ сделано | 5 | новая `POST /organizations/{organization_id}/verification` | Should | clients, enrichment, decision |
| 4.3 | ✅ Личные согласия: ПДн и БКИ физлица | 8 | новые `GET/POST /me/consents`, `DELETE /me/consents/{type}` | Should, вместе с 4.4 | identity, clients, process |
| 4.4 | ✅ Источники ГИР БО, Контур, БКИ ФЛ | 10 | без новых ручек: расширяется `EnrichmentSnapshotDTO` | Should | enrichment, decision, process, external-mocks |
| 4.5 | ✅ Договор перед подписью | 17 | новая `GET /applications/{id}/contract`, `offer_hash` в `sign` | Should | applications |
| 4.6 | Ветка стартапа | 3, ветка «нет» | новые `…/founder-prescreen`, поле `segment` на дашборде | Could | clients, scoring, process, products |
| 4.7 | ✅ Скоринг и стратегия как на схеме | 12–13 | без новых ручек: поля в DTO андеррайтера | Could | scoring, decision |

Must нет: основной путь (компания с оборотами в банке) проходит и сейчас. Всё ниже закрывает расхождения со схемой.

### 4.1. Калькулятор с учётом предскоринга

✅ Сделано, контракт — в [3.4](#34-выбор-условий-шаг-7).

**Зачем.** На схеме: «Сумма, срок, платёж — это калькулятор, только с учётом предскоринга, чтобы не предложить 30 млн на слоты». Публичный `POST /products/{code}/calculate` про компанию не знает: считает любую сумму в рамках продукта по базовой ставке. Если собирать ответ на фронте из `/bff/products/recommend` (`pre_approved_max`) и `calculate` с `rate = rate_from`, правило «не больше предодобренного» жило бы на фронте.

**Ручка.** `POST /bff/products/{code}/calculate?organization_id=…`. Нужен вход и `credits.read`, чужая компания — 404. Ручка в BFF, а не в products: предодобрение хранит `decision`, а он сам читает `products`, и получился бы цикл.

**Как считает.** Компания видна пользователю → `ProductsFacade.get_product` и `check_eligibility` → рамки продукта (422) → `DecisionFacade.get_pre_approved`, предложение по `code` → `ProductsFacade.calculate_payment` по `rate_from` или `rate_base`; второй расчёт — для `suggestion`.

Подачу сверх предодобренного не блокируем ни на бэке, ни на фронте: только причина и подсказка.

### 4.2. Сверка с ЕГРЮЛ

**Сделано.** На схеме: «Сверили данные с ЕГРЮЛ → данные изменились → подкачали новые». Сверка запускается ручкой и сама — после сбора данных по каждой заявке.

**Ручка.** `POST /organizations/{organization_id}/verification`, без тела. Право — `organizations.update`: клиент — любой участник компании, андеррайтер — любая компания. Реестр спрашиваем мимо кэша.

Ответ 200 `VerificationResultRead`:

```json
{
  "organization": { "…": "OrganizationRead с новым verification и version" },
  "updated_fields": [
    { "field": "address.full", "before": "г. Москва, ул. Тверская, д. 12, стр. 1", "after": "г. Москва, ул. Тверская, д. 1" }
  ],
  "discrepancies": [
    { "field": "head_name", "declared": "Петров П. П.", "registry": "Сидоров С. С." }
  ]
}
```

| Поле реестра | Что делаем | `field` |
|---|---|---|
| наименование | обновляем молча → `updated_fields`. Реестр отдаёт полное наименование, храним краткое: «Общество с ограниченной ответственностью «Ромашка»» → «ООО «Ромашка»» | `name` |
| адрес | обновляем молча | `address.full`, `address.region_code` |
| КПП | обновляем молча; реестр не назвал КПП — оставляем | `kpp` |
| ОКВЭД основной и дополнительные | обновляем молча; те же коды в другом порядке — не изменение | `okved_main`, `okved_extra` (коды через «, ») |
| статус в реестре | обновляем молча; стоп-фактор применяет decision | `registry_status` |
| руководитель | молча не меняем: от него зависят полномочия → `discrepancies`, `verification.status = mismatch` | `head_name` |
| ИНН, ОГРН | не меняются, это ключ компании | — |

Расхождение по руководителю бывает двух видов:
- в реестре другой руководитель, чем знает банк: `declared` — прежний руководитель по реестру;
- руководитель в кабинете (директор, у ИП — владелец) с другим ФИО, чем в реестре: `declared` — его ФИО. Так у «Вектора»: в кабинете Петров, в реестре Сидоров.

Нет расхождений — `verified`. Заявка с `mismatch` уходит на ручную проверку (`ROUTE_VERIFICATION_MISMATCH`).

| Код | Когда |
|---|---|
| 404 `not_found` | компании нет или она чужая |
| 422 `validation_error`, `details.code = registry_not_found` | реестр не знает этот ИНН |
| 503 `unavailable` | реестр не ответил или ответил тем, что не разобрать (`details.code = bad_registry_data`); сверка не меняется |

**Автосверка.** После каждого `EnrichmentCompleted` бэк сверяет компанию по выписке ЕГРЮЛ из снимка заявки — без лишнего запроса в реестр. Источник ЕГРЮЛ не ответил — сверка пропускается. Фронту отдельно ничего делать не нужно: свежий результат — в `OrganizationRead.verification`.

**После сверки.** Уходит `OrganizationVerified` или `OrganizationVerificationMismatch`. На оба подписан пересчёт предодобрения: `pre_approved` обновится сам. В ленте участников появится запись о сверке; при расхождении — `info_requested` со списком расхождений.

Андеррайтер с `organizations.update` больше ничего в компании не меняет: участники, доверенности и отчёты — 403, `details.code = not_a_member`.

### 4.3. Личные согласия: ПДн и БКИ физлица

✅ Ручки есть (identity). Кредитную историю физлица по 218-ФЗ можно запросить только с согласия самого человека, а согласия в черновике заявки (`consents.personal_data`, `consents.credit_bureau` — БКИ компании) даёт тот, кто её заполняет, а это может быть бухгалтер. Поэтому личные согласия живут на аккаунте, а не на заявке.

| Ручка | Тело | Ответ |
|---|---|---|
| `GET /me/consents` | — | `ConsentRead[]`: действующие и история, новые сверху |
| `POST /me/consents` | `{"types": ["personal_data", "credit_bureau_personal"]}` | 201 `ConsentRead[]` — данные согласия |
| `DELETE /me/consents/{type}` | — | 204; повторный отзыв или отзыв не данного согласия — тоже 204 |

Нужен только вход: согласие человек даёт за себя, пермишн не нужен.

```text
ConsentRead {
  type: "personal_data" | "credit_bureau_personal"
  given_at: date-time
  valid_until: date-time | null // personal_data — бессрочно (null), credit_bureau_personal — 6 календарных месяцев
  revoked_at: date-time | null
  active: boolean               // не отозвано и срок не истёк
  text_version: string          // редакция текста согласия, которую показали
}
```

- История не перезаписывается: каждое `POST` — новая строка, отзыв только ставит `revoked_at` действующим согласиям этого типа. Истёкшее согласие при отзыве не трогаем: оно закончилось само.
- Повторное `credit_bureau_personal` до истечения продлевает срок: действует самое свежее.
- С согласием хранятся IP и `User-Agent` запроса — доказательство, кто и откуда его дал.
- Неизвестный тип в `POST` или `DELETE` — 422.

Как согласие доходит до запроса в БКИ: при сборке `FetchEnrichment` процесс находит руководителя по реестру (`ClientsFacade.get_registry_head` — участник, чьё ФИО совпало с руководителем в ЕГРЮЛ) и его действующее согласие (`IdentityFacade.get_active_consent`). В команду уходят `head` и `head_bki_consent_at`; без согласия — `head_bki_consent_at = null`, и БКИ руководителя не запрашивается ([4.4](#44-источники-гир-бо-контур-бки-физлица)).

Что видно на экранах ([3.3](#33-главная-компания-и-предодобрение-шаги-36), [3.6](#36-пока-банк-думает-шаги-1015-глазами-клиента)):
- в карточке заявки — `consents.head_credit_bureau: {required, given, given_at, head_name}`, чтобы показать «руководитель ещё не дал согласие»;
- в `Dashboard.todo` руководителю — `kind: consent_required`, пока есть заявка до решения, а его согласия нет.

### 4.4. Источники ГИР БО, Контур, БКИ физлица

✅ Блок «Запросы» схемы: ГИР БО (бухотчётность), Контур (суды, приставы, банкротство), ФНС (налоговые долги, блокировки), БКИ компании, БКИ руководителя. Процесс просит у enrichment все источники, БКИ руководителя — только с его личным согласием ([4.3](#43-личные-согласия-пдн-и-бки-физлица)).

**Новых ручек нет.** Расширился `EnrichmentSnapshotDTO` в `GET /bff/backoffice/applications/{id}` (`UnderwriterCard.enrichment`):

```text
sources_ok[], sources_failed[].source:  + "gir_bo" | "kontur" | "bki_head"
sources_skipped: [{ source, code, message }]   // не запрошены: bki — no_consent; bki_head — no_consent | no_head

gir_bo: {
  available: boolean, reason: string | null,   // нет отчётности: ИП, компания младше года
  periods: [{ year, revenue, cost_of_sales, sales_profit, interest_payable, net_profit,
              fixed_assets, inventories, receivables, cash, equity, total_assets,
              long_term_liabilities, short_term_liabilities, total_liabilities }]
} | null                                       // рубли строками, от старого года к новому

kontur: {
  reliability: "green" | "yellow" | "red", notes: string[],
  arbitration: { as_defendant, as_plaintiff, defendant_sum },
  enforcement: { active, sum },
  bankruptcy_messages: [{ date, type, case }],
  gov_contracts: { count, sum },
  active_pledges: int
} | null

bki_head: CreditHistoryDTO | null              // та же схема, что у bki компании

fns.account_blocks: [{ decision_number, date, authority_code, reason }]
```

Стоп-факторы — новая версия политики `policy_v2` (её номер — в `decision.policy_version` карточки андеррайтера). Пороги стартовые и живут в YAML:

| Условие | Источник | Причина |
|---|---|---|
| сообщения о банкротстве | Контур | `STOP_BANKRUPTCY_MESSAGE` |
| действующие блокировки счетов | ФНС | `STOP_ACCOUNT_BLOCKS` |
| исполнительные производства > 10% годовой выручки | Контур | `STOP_LARGE_ENFORCEMENT` |
| иски к компании > 20% годовой выручки | Контур | `STOP_LARGE_LAWSUITS` |
| отрицательный собственный капитал в последнем периоде | ГИР БО | `STOP_NEGATIVE_EQUITY` |
| текущая просрочка руководителя 30+ дней | БКИ руководителя | `STOP_HEAD_OVERDUE` |
| текущая просрочка компании 30+ дней | БКИ | `STOP_CURRENT_OVERDUE` |
| налоговая недоимка > 300 000 ₽ | ФНС | `STOP_TAX_ARREARS` |
| адрес массовой регистрации | ЕГРЮЛ | `STOP_MASS_ADDRESS` |
| основной ОКВЭД из стоп-листа банка | ЕГРЮЛ | `STOP_FORBIDDEN_OKVED` |
| налоговая недоимка > 0, но не выше порога | ФНС | `ROUTE_TAX_ARREARS` — на ручную проверку |

Клиент видит только итог: текст отказа без деталей источников. Если источник не ответил, решение уходит на ручную проверку (`ROUTE_SOURCES_FAILED`), и клиент читает, что заявку рассмотрит специалист. Нет согласия руководителя — его БКИ не запрашивается, проверка просрочки руководителя пропускается, решение идёт дальше.

В external-mocks — `GET /gir-bo/{inn}`, `GET /kontur/{inn}`, `POST /bki/person-report` и `account_blocks` в `GET /fns/{inn}`; формы ответов — как в `frontend/mocks/external-sources.json`.

### 4.5. Договор перед подписью

✅ Сделано, контракт — в [3.7](#37-решение-оффер-подпись-выдача-шаги-1518).

- `GET /applications/{id}/contract` отдаёт договор с `signing` и дальше: заёмщик, подписанты, условия оффера, график платежей и подпись.
- `POST /applications/{id}/sign` принимает `{password, offer_hash}`; изменившийся оффер — 409 `offer_changed`.
- Адреса заёмщика в договоре нет: его нет в снимке компании, который заявка фиксирует при подаче.
- PDF не генерируем, фронт рендерит договор из полей.

### 4.6. Ветка стартапа

**Зачем.** Ветка «Есть ли бизнес? — нет (стартап)»: личный скоринг учредителя (предскрин) → отказ или загрузка бизнес-плана и финмодели → проектная оценка (бизнес-план, обеспечение, господдержка) → предложение. Её нет совсем. При этом [case.md](../case.md) §5 (ответ организаторов) говорит, что предприниматель уже клиент банка и онбординга нет. Поэтому приоритет Could: делаем, только если ветку показываем на демо.

**Изменения API:**
- `Dashboard.organization.segment: "established" | "startup"`. `startup` — нет оборотов в банке и годовой отчётности. Для стартапа `pre_approved` пуст, вместо него приходит `startup: {prescreen: FounderPrescreenRead | null}`.
- `POST /organizations/{organization_id}/founder-prescreen`, без тела. Нужно действующее `credit_bureau_personal` учредителя (4.3), иначе 422 `consent_required`.
- `GET /organizations/{organization_id}/founder-prescreen` — последний результат или 404.

```json
{
  "status": "passed",
  "founder": { "account_id": "…", "name": "…" },
  "checked_at": "…",
  "valid_until": "…",
  "reasons": [{ "code": "…", "passed": true, "message": "…" }]
}
```

`status = failed` — это «Отказ (стартап)» на схеме: клиенту показываем `reasons[].message`.

**Без новых ручек:**
- Бизнес-план и финмодель — продукт `STARTUP` с `required_documents` `business_plan` и `financial_model`, `min_business_age_months = 0`. Грузятся обычными `/applications/{id}/documents`.
- Проектная оценка — шаг процесса `STARTUP`, задача андеррайтеру через `/tasks`. Её результат — обычный оффер. Господдержка — `product.support_program`.

### 4.7. Скоринг и стратегия как на схеме

Сделано: PD-модель `pd_model_v2` ([scoring.md](../modules/scoring.md)) и политика `policy_v3` ([decision.md](../modules/decision.md)). Клиентских ручек это не меняет: клиент видит только исход, условия и объяснение. Новые поля — в DTO андеррайтера `UnderwriterCard.scoring` и `UnderwriterCard.decision`:

```text
scoring: {
  …, grade: "A" … "J",                     // было A–E: шкала поменялась
  segment: legal_entity | entrepreneur | new_client | null,   // null — результат до pd_model_v2
  scorecard: string | null,                // legal_entity_v1 | entrepreneur_v1 | new_client_v1
  pd_12m: string | null,                   // доля: "0.0345" — 3,45%
  reason_codes: string[]                   // топ-3 признака по потере баллов: "debt_load", …
}
decision: {
  …,
  limits: { by_revenue, by_ltv, by_capacity, by_product, by_turnover, by_grade, by_group, final,
            binding: string | null },      // binding — какое ограничение дало минимум
  triggers: [{ code: tax_arrears | head_change | turnover_spike, detail }],
  rate_breakdown: { funding, expected_loss, capital, margin, total } | null   // проценты годовых
}
```

- Матрица грейд × сумма и мягкие триггеры видны в `rule_trace` (`strategy.risk_matrix`, `trigger.*`), причины — `ROUTE_RISK_MATRIX`, `STOP_RISK_MATRIX`, `ROUTE_SOFT_TRIGGER`, `LIMIT_BY_TURNOVER`, `LIMIT_BY_GRADE`, `LIMIT_BY_GROUP`.
- `QueueItemDTO.risk_grade` в очереди андеррайтера — тоже A–J.
- Встречное предложение: сначала удлиняем срок в рамках продукта, потом снижаем сумму — контракт тот же. Поручительство для F–G и сумм больше 20 млн — в `offer.conditions`.
- Ночной пакетный пересчёт предодобрения не сделан: пересчёт по событиям clients, контракт тот же.

В моке админки третья шкала: `RiskClass` A–D и балл 0–100. Её надо привести к A–J и PD бэка.

---

## 5. Админка фронта на моках и бэк

Это вне клиентского пути, но тоже контракт для фронта. `creditApi` (`frontend/src/shared/api/credit/types.ts`) целиком на моке, и его методы не совпадают с ручками бэка:

| Метод мока | Ручка бэка | Расхождение |
|---|---|---|
| `listApplications(filters)` | `GET /bff/backoffice/queue`, `GET /applications?status=` | мок — все заявки с поиском; бэк — очередь задач андеррайтера, поиска (`search`) нет |
| `getApplication(id)` | `GET /bff/backoffice/applications/{id}` | `dossier` мока ≈ `enrichment` бэка; поля разные, ГИР БО и Контура нет (4.4) |
| `assign(id)` | `POST /tasks/{task_id}/claim` | по задаче, а не по заявке |
| `decide(id, input)` | `POST /tasks/{task_id}/complete` | по задаче; словарь исходов: мок `approved / counter_offer / info_requested / rejected` ↔ бэк `approve / counter_offer / request_info / reject` |
| `transition(id, to_signing \| issue)` | — | переходы делают клиент (`accept`, `sign`) и процесс (выдача); у банка таких ручек нет |
| `getDashboard()` | `GET /bff/backoffice/metrics` | у бэка нет `overdue`, `inProgress`, `approvedVolume`, `averageAmount`, `byStatus`, `byRisk`, `funnel` |
| `rescore(id)` | — | ❌ |
| `lookupInn(inn, amount)` | — | ❌ проверка компании по ИНН с предскорингом |
| `listProducts()` / `updateProduct()` | `GET /products` / — | ❌ каталог не редактируется |
| `getScoringConfig()` / `updateScoringConfig()` / `previewScoring()` | — | ❌ политика — YAML (`backend/src/modules/decision/infrastructure/config/policy_v1.yaml`), ручек нет |
| `resetDemoData()` | — | только для мока |

Что из ❌ делать на бэке, а что оставить моком, — отдельное решение. Там, где ручки есть, мок стоит перевести на них.
