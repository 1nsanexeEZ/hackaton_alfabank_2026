# Модель данных

Какие таблицы есть в Postgres, кому они принадлежат и как связаны. Схема собрана по ORM-моделям (`backend/src/modules/*/infrastructure/database/models.py`, в `products`, `scoring`, `decision` — `infrastructure/models.py`; все они импортируются в `backend/src/models.py`). Всего 46 таблиц и две последовательности для номеров (`applications_number_seq` — «КР-<год>-<NNNNNN>», `support_ticket_number_seq`). На диаграммах показаны ключевые поля, полный список колонок — в моделях. Миграции — Alembic: одна цепочка ревизий с именем модуля (`applications_0006`, `decision_0006`, `process_0003`…) и одна голова (сейчас `notifications_0002`); CI проверяет upgrade → downgrade → upgrade и `alembic check`.

## Правила

- **Одна база, свои таблицы у каждого модуля.** Имя таблицы начинается с имени модуля (`applications_…`, `decision_…`). Исключения — исторические таблицы identity: `accounts`, `profiles`, `roles` — и общие таблицы обмена `core_outbox`, `core_inbox`.
- **Внешние ключи — только внутри модуля.** Между модулями — идентификатор по значению (`organization_id`, `application_id`) без FK: модуль не знает чужих таблиц, а данные соседа читает через фасад. Так модуль можно вынести в отдельную базу без переделки схемы.
- **Снимки, а не ссылки, там, где важна история.** Заявка хранит копию условий продукта (`product_terms`) и снимок компании на момент подачи (`org_snapshot`). Решение хранит свои входы (`inputs`), скоринг — `input_snapshot` и его хеш. Правка каталога или карточки компании не меняет рассмотренную заявку, решение можно воспроизвести.
- **Только добавление** там, где нужен след: история статусов, журнал подписания с хеш-цепочкой, версии моделей и политик, решения (новое решение — новая строка с `sequence`).
- **Оптимистичная блокировка** (`version`) у агрегатов, которые меняют параллельно: заявка, компания, процесс, задача, обращение.
- **JSONB** для вложенных value objects (предложение, залог, согласия, трасса правил) — они меняются вместе с агрегатом и не нужны в отдельных запросах.

## Клиент: identity и clients

```mermaid
erDiagram
    roles ||--o{ accounts : "role_id"
    accounts ||--|| profiles : "account_id"
    accounts ||--o{ identity_consents : "account_id"
    clients_organizations ||--o{ clients_members : "organization_id"
    clients_organizations ||--o{ clients_financial_reports : "organization_id"
    clients_organizations ||--o| clients_business_plans : "organization_id"
    accounts ||..o{ clients_members : "account_id (без FK)"

    roles {
        uuid id PK
        string name
        json permissions
        json policies
    }
    accounts {
        uuid id PK
        string email
        string phone
        string password_hash
        uuid role_id FK
        timestamp deleted_at
    }
    profiles {
        uuid account_id PK
        string last_name
        string first_name
        string middle_name
        string position
    }
    identity_consents {
        uuid id PK
        uuid account_id FK
        uuid organization_id
        string type
        timestamp given_at
        timestamp valid_until
        timestamp revoked_at
        string text_version
        string ip
        string user_agent
        uuid revoked_by
    }
    clients_organizations {
        uuid id PK
        string inn
        string ogrn
        string legal_form
        string name
        date registered_at
        string okved_main
        string registry_status
        json registry_head
        string verification_status
        json verification_discrepancies
        int version
    }
    clients_members {
        uuid organization_id PK
        uuid account_id PK
        string role
        string authority
        json power_of_attorney
        timestamp added_at
    }
    clients_financial_reports {
        uuid id PK
        uuid organization_id FK
        int period_year
        int period_quarter
        string source
        numeric revenue
        numeric net_profit
    }
    clients_business_plans {
        uuid organization_id PK
        text summary
        json financial_model
        int revision
    }
```

- **Согласия** — история: новое согласие — новая строка, отзыв ставит `revoked_at`. С согласием хранятся редакция текста, IP и `User-Agent` (152-ФЗ ст. 9, 218-ФЗ ст. 6). `organization_id` заполнен у согласия компании на запрос её кредитной истории.
- **Права в компании** — `clients_members.role` + `authority` (`registry` — руководитель по ЕГРЮЛ) + `power_of_attorney` (номер, срок, объём прав).
- **Отчётность** — `source`: `declared` (клиент), `fns`, `bank_statement`. При сборке снимка источники идут по приоритету.

## Заявка: applications

```mermaid
erDiagram
    applications_applications ||--o{ applications_documents : ""
    applications_applications ||--o{ applications_info_requests : ""
    applications_applications ||--o{ applications_status_history : ""
    applications_applications ||--o| applications_signatures : ""
    applications_applications ||--o{ applications_contract_documents : ""
    applications_applications ||--o{ applications_contract_events : ""
    applications_info_requests ||..o{ applications_documents : "info_request_id"

    applications_applications {
        uuid id PK
        string number
        uuid organization_id
        uuid applicant_account_id
        string product_code
        string status
        string client_stage
        json product_terms "копия условий продукта"
        json request "сумма, срок, цель"
        json product_fields "поля продукта по JSON Schema"
        json collateral
        json consents "ПДн, БКИ, авторешение"
        json beneficiary "выгодоприобретатель, 115-ФЗ"
        json beneficial_owners
        json org_snapshot "компания на момент подачи"
        json offer
        json decision_summary
        string decided_by "авто / андеррайтер, для фильтра списка"
        json disbursement
        timestamp offer_expires_at
        timestamp submitted_at
        timestamp closed_at
        int version
    }
    applications_documents {
        uuid id PK
        uuid application_id FK
        string type
        string s3_key
        string status "pending_upload / uploaded / accepted / rejected"
        uuid info_request_id
    }
    applications_info_requests {
        uuid id PK
        uuid application_id FK
        json requested_fields
        json requested_documents
        string status "open / answered / expired"
        timestamp due_at
    }
    applications_status_history {
        bigint id PK
        uuid application_id FK
        string from_status
        string to_status
        timestamp at
        string actor_type
        uuid actor_id
        string reason
    }
    applications_signatures {
        uuid application_id PK
        uuid signed_by
        timestamp signed_at
        string offer_hash
        string document_hash
        string rules_version
        string ip
        string user_agent
        string edo_document_id
    }
    applications_contract_documents {
        uuid id PK
        uuid application_id FK
        string kind "draft / signed"
        string offer_hash
        string sha256
        string storage_key
        json seal "подпись банка: сертификат, время"
    }
    applications_contract_events {
        bigint id PK
        uuid application_id FK
        int seq
        string kind
        string actor
        json details
        string prev_hash
        string hash
    }
```

- **Статус** меняет только агрегат `CreditApplication`, каждый переход — строка в `applications_status_history` ([state-machine.md](state-machine.md)).
- **Документы** — метаданные. Файлы лежат в MinIO (`credit-documents`), загрузка по presigned URL с подтверждением.
- **Договор** — `applications_contract_documents` (файлы в бакете `credit-contracts` с Object Lock), журнал подписания — хеш-цепочка `prev_hash → hash` ([contract-signing.md](contract-signing.md)).

## Процесс: process

```mermaid
erDiagram
    process_workflow_definitions ||--o{ process_instances : "workflow_hash"
    process_instances ||--o{ process_step_executions : ""
    process_instances ||--o{ process_user_tasks : ""

    process_workflow_definitions {
        string source_hash PK
        string code
        int version
        text source "BPMN XML"
    }
    process_instances {
        uuid id PK
        uuid application_id "UNIQUE: один процесс на заявку"
        string workflow_code
        int workflow_version
        string workflow_hash FK
        string status
        string current_node_id
        json waiting
        timestamp waiting_since
        json context
        json iterations
        int version
    }
    process_step_executions {
        uuid id PK
        uuid process_id FK
        string node_id
        string step_code
        string kind
        int iteration
        string outcome
        uuid command_event_id
        string error
    }
    process_user_tasks {
        uuid id PK
        uuid process_id FK
        uuid application_id
        string node_id
        string type
        string candidate_role
        json form_schema
        string status
        uuid assignee_id
        json result
        string reason "причина ручной проверки"
        timestamp due_at
        int version
    }
```

Экземпляр процесса ссылается на BPMN по хешу исходника: правка файла маршрута не меняет граф уже идущих процессов. `command_event_id` шага — `event_id` отправленной команды. Принимается только ответ с таким `causation_id`.

## Оценка и решение: enrichment, scoring, decision

```mermaid
erDiagram
    enrichment_snapshots ||--o{ enrichment_source_results : ""
    enrichment_snapshots ||..o{ scoring_feature_snapshots : "enrichment_snapshot_id"
    scoring_model_versions ||..o{ scoring_results : "model_version"
    decision_policy_versions ||..o{ decision_results : "policy_version"

    enrichment_snapshots {
        uuid id PK
        uuid application_id
        uuid organization_id
        string inn
        uuid requested_by_command "UNIQUE: повтор команды — тот же снимок"
        json requested_sources
        timestamp started_at
        timestamp completed_at
    }
    enrichment_source_results {
        uuid snapshot_id PK
        string source PK "egrul fns bki bki_head gir_bo kontur aml bank_turnover bank_stop_list statement"
        string status "ok failed skipped"
        int latency_ms
        int attempts
        json data
        string error_kind
    }
    scoring_feature_snapshots {
        uuid id PK
        uuid organization_id
        date as_of
        uuid enrichment_snapshot_id
        json features
        string version
    }
    scoring_results {
        uuid id PK
        uuid application_id
        string model_version
        json input_snapshot
        string input_hash
        int score
        string segment
        numeric pd_12m
        string grade
        json reason_codes
        json ml
        string ml_not_applicable
        string quality
    }
    scoring_model_versions {
        string version PK
        string status
        json body
        string based_on
        uuid created_by
        uuid activated_by
    }
    decision_results {
        uuid id PK
        uuid application_id
        int sequence
        string policy_version
        numeric key_rate
        json inputs
        string outcome
        json terms
        json reason_codes
        json rule_trace
        json limits
        json rate_breakdown
        string decided_by_type
        uuid override_of "ручное решение указывает на автоматическое"
    }
    decision_policy_versions {
        string version PK
        string status
        json body
        string based_on
        uuid created_by
        uuid activated_by
    }
    decision_pre_approved_offers {
        uuid organization_id PK
        string product_code PK
        numeric max_amount
        numeric rate_from
        int term_max_months
        string basis "estimate / project"
        date valid_until
        numeric key_rate "ключевая, с которой посчитано; NULL — проектное или до decision_0006"
    }
    decision_founder_prescreens {
        uuid id PK
        uuid organization_id
        uuid founder_account_id
        string status
        json reasons
        timestamp checked_at
        timestamp valid_until
    }
    decision_project_assessments {
        uuid id PK
        uuid organization_id
        string product_code
        int plan_revision
        string status
        json figures
        numeric max_amount
        timestamp checked_at
        timestamp valid_until
    }
```

- **Воспроизводимость.** `scoring_results.input_snapshot` + `input_hash` + `model_version` и `decision_results.inputs` + `policy_version` + `key_rate` позволяют пересчитать решение той же версией и получить тот же результат.
- **Ручное решение** — новая строка `decision_results` с `decided_by_type = underwriter` и `override_of` — ссылкой на автоматическое.
- **Версии админа** (`scoring_model_versions`, `decision_policy_versions`): встроенные версии живут в YAML, в БД — только созданные администратором (`pd_model_v2.1`, `policy_v10.1`…).

## Лента, поддержка, помощник, обмен

```mermaid
erDiagram
    notifications_news_items ||--o{ notifications_news_reads : ""
    support_tickets ||--o{ support_messages : ""

    notifications_feed_items {
        uuid id PK
        bigint seq
        uuid source_event_id
        string recipient_type "account / role"
        string recipient_id "id аккаунта или имя роли"
        string type
        string title
        bool action_required
        uuid organization_id
        uuid application_id
        timestamp read_at
    }
    notifications_news_items {
        uuid id PK
        string slug
        json okved_prefixes
        json product_codes
        json legal_forms
        bool is_general
    }
    notifications_news_reads {
        uuid news_id PK
        uuid account_id PK
        timestamp read_at
    }
    notifications_stream_tickets {
        uuid id PK
        string ticket_hash
        uuid account_id
        timestamp expires_at
        timestamp used_at
    }
    support_tickets {
        uuid id PK
        string number
        string subject
        string status
        uuid owner_id
        uuid organization_id
        uuid application_id
        uuid assignee_id
        timestamp taken_at
        timestamp resolved_at
        timestamp closed_at
        int version
    }
    support_messages {
        uuid id PK
        uuid ticket_id FK
        int position
        uuid author_id
        string side
        text text
    }
    core_outbox {
        uuid id PK
        uuid event_id
        string topic
        string key
        string message_type
        json envelope
        timestamp published_at
        int attempts
    }
    core_inbox {
        string consumer PK
        uuid event_id PK
        timestamp processed_at
    }
```

История умного помощника — таблицы модуля `assistant`: диалог видит только его автор (`owner_id`), в сообщении — роль (вопрос или ответ), заявка, намерение и режим ответа (`llm` или `rules`). Тексты вопросов и ответов в логи не пишутся ([ai.md](ai.md)).

```mermaid
erDiagram
    assistant_conversations ||--o{ assistant_messages : ""

    assistant_conversations {
        uuid id PK
        uuid owner_id
        timestamp created_at
    }
    assistant_messages {
        uuid id PK
        uuid conversation_id FK
        int position
        string role
        text text
        uuid application_id
        string intent
        string mode
        timestamp created_at
    }
```

## Модели чтения: projector

Денормализованные таблицы под экраны. Их можно удалить и перестроить из Kafka (`backend/scripts/projector_rebuild.py`, [projector.md](modules/projector.md)); связей между ними нет.

```mermaid
erDiagram
    projector_application_overview {
        uuid application_id PK
        uuid organization_id
        string number
        string product_code
        string status
        string client_stage
        string action_required
        numeric offer_amount
        numeric offer_rate
        string decision_outcome
        string decided_by
        int time_to_decision_sec
        int source_version
    }
    projector_underwriting_queue {
        uuid task_id PK
        uuid application_id
        string candidate_role
        string status
        timestamp due_at
        numeric amount
        int score
        string risk_grade
        bool cash_gap
        json routing_reasons
        string review
        int source_version
    }
    projector_application_timeline {
        uuid id PK
        uuid application_id
        uuid source_event_id "UNIQUE"
        timestamp at
        string kind
        string title
        string audience
        json details
    }
    projector_organization_dashboard {
        uuid organization_id PK
        int active_applications
        int action_required_count
        numeric pre_approved_max_amount
        numeric pre_approved_rate_from
        timestamp last_activity_at
    }
    projector_backoffice_metrics {
        date day PK
        string product_code PK
        int submitted
        int approved
        int counter_offers
        int rejected
        int manual_reviews
        int auto_decisions
        bigint decision_time_total_sec
        int decision_time_count
    }
```

- `projector_application_overview` — «Мои заявки» и источник метрик, строка на заявку;
- `projector_underwriting_queue` — строка на задачу процесса, открытую или закрытую;
- `projector_application_timeline` — этапы заявки, клиенту отдаются только с `audience` для клиента;
- `projector_organization_dashboard` — счётчики и предодобрение для главной компании;
- `projector_backoffice_metrics` — счётчики по продукту за сутки UTC.

## Ключевая ставка: market

`market_key_rates` — ключевая ставка Банка России с даты, по строке на дату смены. Ограничение: `value` от 0 до 100.

```mermaid
erDiagram
    market_key_rates {
        date effective_from PK
        numeric value "% годовых"
        date decided_on
        string source "admin / cbr"
        text note
        uuid created_by
        timestamp created_at
        timestamp announced_at "когда ушло KeyRateChanged"
    }
```

На дату действует строка с наибольшим `effective_from` не позже её; строк нет — `KEY_RATE` из настроек. Строки, уже вступившие в силу, не меняются и не удаляются; ещё не вступившую можно отозвать (`DELETE /market/key-rates/{effective_from}`) — [market.md](modules/market.md).

## Каталог продуктов: products

`products_credit_products` — продукт с версией и статусом (`draft` / `active` / `archived`), уникальны `(code, version)`:

```mermaid
erDiagram
    products_credit_products {
        uuid id PK
        string code "UNIQUE с version"
        int version
        string status "draft / active / archived"
        int sort_order
        string frontend_id
        json keywords
        string tag
        string decision_time
        string name
        string short_description
        text description_plain
        json purposes
        string facility
        json repayment_options
        numeric amount_min
        numeric amount_max
        int term_min_months
        int term_max_months
        numeric rate_base
        numeric rate_max
        string collateral_kind
        json collateral_types
        numeric collateral_required_from
        string guarantee
        bool target_use_confirmation
        json support_program
        int min_business_age_months
        json allowed_legal_forms
        numeric min_annual_revenue
        bool startup_only
        json required_documents
        json application_fields_schema
        string workflow_code
        numeric auto_decision_limit
    }
```

- рамки суммы и срока, коридор ставки (`rate_base`…`rate_max`);
- цели, форма, графики погашения;
- обеспечение и господдержка;
- требования к заёмщику: возраст бизнеса, формы, выручка, признак «только стартап»;
- документы и JSON Schema дополнительных полей;
- маршрут (`workflow_code`) и лимит авторешения;
- поля витрины сайта: `sort_order`, `frontend_id`, `keywords`, `tag`, `decision_time`.

Новая редакция условий — новая версия, прежняя уходит в архив; заявка хранит копию условий на момент подачи. Каталог — [credit-products.md](product/credit-products.md).
