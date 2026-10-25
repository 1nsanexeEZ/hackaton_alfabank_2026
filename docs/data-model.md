# Модель данных

Какие таблицы есть в Postgres, кому они принадлежат и как связаны. Схема собрана по ORM-моделям (`backend/src/modules/*/infrastructure/database/models.py`), миграции — Alembic: одна цепочка ревизий с именем модуля (`applications_0005`, `decision_0007`…) и одна голова; CI проверяет upgrade → downgrade → upgrade и `alembic check`.

## Правила

- **Одна база, свои таблицы у каждого модуля.** Имя таблицы начинается с имени модуля (`applications_…`, `decision_…`). Исключение — исторические таблицы identity: `accounts`, `profiles`, `roles`.
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
        int version
    }
    clients_members {
        uuid organization_id PK
        uuid account_id PK
        string role
        string authority
        json power_of_attorney
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
        json summary
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
        json collateral
        json consents "ПДн, БКИ, авторешение"
        json beneficiary "выгодоприобретатель, 115-ФЗ"
        json beneficial_owners
        json org_snapshot "компания на момент подачи"
        json offer
        json decision_summary
        timestamp offer_expires_at
        int version
    }
    applications_documents {
        uuid id PK
        uuid application_id FK
        string type
        string s3_key
        string status
        uuid info_request_id
    }
    applications_info_requests {
        uuid id PK
        uuid application_id FK
        json requested_fields
        json requested_documents
        string status
        timestamp due_at
    }
    applications_status_history {
        uuid id PK
        uuid application_id FK
        string from_status
        string to_status
        timestamp at
        string actor_type
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
        string edo_document_id
    }
    applications_contract_documents {
        uuid id PK
        uuid application_id FK
        string kind "draft / signed"
        string offer_hash
        string sha256
        string storage_key
        json seal
    }
    applications_contract_events {
        uuid id PK
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
        uuid application_id
        string workflow_code
        string status
        string current_node_id
        json waiting
        json context
        json iterations
        int version
    }
    process_step_executions {
        uuid id PK
        uuid process_id FK
        string node_id
        string step_code
        int iteration
        string outcome
        uuid command_event_id
        string error
    }
    process_user_tasks {
        uuid id PK
        uuid process_id FK
        uuid application_id
        string type
        string candidate_role
        json form_schema
        string status
        uuid assignee_id
        json result
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
        json requested_sources
        timestamp completed_at
    }
    enrichment_source_results {
        uuid snapshot_id PK
        string source PK "egrul fns bki bki_head gir_bo kontur aml bank_turnover bank_stop_list statement"
        string status "ok failed skipped"
        int latency_ms
        int attempts
        json data
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
        string segment
        numeric pd_12m
        string grade
        json reason_codes
        json ml
        string quality
    }
    scoring_model_versions {
        string version PK
        string status
        json body
        string based_on
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
    }
    decision_policy_versions {
        string version PK
        string status
        json body
        string based_on
    }
    decision_pre_approved_offers {
        uuid organization_id PK
        string product_code PK
        numeric max_amount
        numeric rate_from
        string basis "estimate / project"
        date valid_until
    }
    decision_founder_prescreens {
        uuid id PK
        uuid organization_id
        uuid founder_account_id
        string status
        json reasons
        date valid_until
    }
    decision_project_assessments {
        uuid id PK
        uuid organization_id
        string product_code
        int plan_revision
        string status
        json figures
        numeric max_amount
        date valid_until
    }
```

- **Воспроизводимость.** `scoring_results.input_snapshot` + `input_hash` + `model_version` и `decision_results.inputs` + `policy_version` + `key_rate` позволяют пересчитать решение той же версией и получить тот же результат.
- **Ручное решение** — новая строка `decision_results` с `decided_by_type = underwriter` и `override_of` — ссылкой на автоматическое.
- **Версии админа** (`scoring_model_versions`, `decision_policy_versions`): встроенные версии живут в YAML, в БД — только созданные администратором (`pd_model_v2.1`, `policy_v10.1`…).

## Лента, поддержка, модели чтения, обмен

```mermaid
erDiagram
    notifications_news_items ||--o{ notifications_news_reads : ""
    support_tickets ||--o{ support_messages : ""

    notifications_feed_items {
        uuid id PK
        bigint seq
        uuid source_event_id
        string recipient_type
        uuid recipient_id
        string type
        string title
        bool action_required
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

Модели чтения `projector_*` — денормализованные таблицы под экраны, их можно удалить и перестроить из Kafka ([architecture.md](architecture/architecture.md#модели-чтения)): `application_overview`, `underwriting_queue`, `application_timeline`, `organization_dashboard`, `backoffice_metrics`.

## Каталог продуктов: products

`products_credit_products` — продукт с версией и статусом (`draft` / `active` / `archived`):
- рамки суммы и срока;
- коридор ставки;
- цели, форма, графики;
- обеспечение и господдержка;
- требования к заёмщику, документы, JSON Schema дополнительных полей;
- маршрут (`workflow_code`) и лимит авторешения.

Новая редакция условий — новая версия, прежняя уходит в архив; заявка хранит копию условий на момент подачи. Каталог — [credit-products.md](product/credit-products.md).
