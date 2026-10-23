# Модуль `enrichment`

## Зачем

Отвечает на вопрос **«что о компании знают внешние источники»** на момент заявки. ТЗ прямо
называет их: бюро кредитных историй, ЕГРЮЛ/ЕГРИП, сервис ФНС «Прозрачный бизнес»; блок «Запросы»
общей схемы добавляет ГИР БО (бухотчётность), Контур (суды, приставы, банкротство) и БКИ
руководителя. Реальных
интеграций нет (автономность), поэтому источники — моки в сервисе `external-mocks` за настоящей
HTTP-границей, а модуль ходит к ним через **ACL-адаптеры**: «чужой» ответ (кириллица, копейки,
даты строками) переводится в наши DTO. Замена мока на реальный API = новый адаптер, домен не
трогаем.

Результат фиксируется **снимком на заявку** (`EnrichmentSnapshot`) с отметкой, что, откуда и когда
получено и что не получилось. Частичный результат (часть источников не ответила) — нормальный
исход, не ошибка: решает это уже `decision`.

Отдельно считает **прогноз кассового разрыва** по банковским выпискам клиента (поле `cashflow`
снимка) — это внутренние данные, а не внешний источник; подробнее ниже.

Не отвечает за: оценку риска (`scoring`), стоп-факторы и выводы (`decision`).

## Структура

Модуль — эталон раскладки по слоям из [settings/04-module-structure.md](../../settings/04-module-structure.md).

```
enrichment/
├── facade.py                 # EnrichmentFacade + реэкспорт DTO для соседей;
│                             # реализация — infrastructure/adapters/enrichment_facade.py
├── module.py                 # wire: HTTP-источники и кеш реестра на процесс, фасад, подписка
├── domain/
│   ├── snapshot.py           # агрегат EnrichmentSnapshot, SourceResult, SourceError
│   ├── cashflow.py           # прогноз кассового разрыва: Transaction, CashflowForecast
│   ├── consent_policy.py     # кого не спрашиваем: no_consent / no_head (218-ФЗ)
│   ├── enums.py              # Source, SourceStatus, INTERNAL_SOURCES
│   └── exceptions.py         # SourceNotFound, SourceUnavailable, StatementParseError
├── application/
│   ├── dto/                  # registry, tax, credit_history, accounting, counterparty, cashflow, snapshot
│   ├── interfaces/           # sources (порты источников + Sources), repositories,
│   │                         # statement_parser, registry_cache
│   └── use_cases/            # fetch_enrichment, build_cashflow, get_snapshot,
│                             # lookup_registry, lookup_person_bureau
├── infrastructure/
│   ├── config.py             # ENRICHMENT_* из окружения
│   ├── adapters/             # *_http.py (ACL к мокам), http_base.py (ретраи), http_sources.py,
│   │                         # statement_csv.py, registry_cache.py, enrichment_facade.py
│   ├── database/             # models
│   └── repositories/         # SqlAlchemyEnrichmentRepository, mappers, serialization (DTO ↔ JSONB)
└── presentation/
    ├── api/, schemas/        # пусто (.gitkeep): HTTP API у модуля нет
    ├── consumers.py          # FetchEnrichment из Kafka → FetchEnrichmentUseCase
    └── dependencies.py       # сборка use case'ов и фасада
```

## Агрегат

`EnrichmentSnapshot` — один снимок на одну команду `FetchEnrichment` (поле `requested_by_command`
уникально). Хранит по каждому источнику `SourceResult` со статусом `ok | failed | skipped`,
задержкой и числом попыток. Сами данные источника для снимка непрозрачны: их форму задают DTO из
`application/dto/`, достаются они типизированно — `snapshot.data_of("egrul", RegistryExtractDTO)`.
Соседям DTO отдаёт `facade.py`.

## Источники

| `Source` | Что | Порт → адаптер | Мок | В снимке |
|---|---|---|---|---|
| `egrul` | ЕГРЮЛ / ЕГРИП: статус, руководитель и дата записи о нём (`head_since`, «Руководитель.ДатаЗаписи» — для мягкого триггера смены руководителя в policy_v3), учредители, адрес | `RegistrySource` → `egrul_http.py` | `GET /egrul/{inn}` | `egrul: RegistryExtractDTO` |
| `fns` | ФНС «Прозрачный бизнес»: недоимка, выручка, блокировки счетов | `TaxSource` → `fns_http.py` | `GET /fns/{inn}` | `fns: TaxProfileDTO` (+ `account_blocks`) |
| `bki` | БКИ компании | `CreditBureauSource` → `bki_http.py` | `POST /bki/report` | `bki: CreditHistoryDTO` |
| `gir_bo` | ГИР БО: бухотчётность за два последних года | `AccountingReportsSource` → `gir_bo_http.py` | `GET /gir-bo/{inn}` | `gir_bo: AccountingReportsDTO` |
| `kontur` | Контур.Фокус: арбитраж, исполнительные производства, банкротство, госконтракты | `CounterpartyRiskSource` → `kontur_http.py` | `GET /kontur/{inn}` | `kontur: CounterpartyRiskDTO` |
| `bki_head` | БКИ руководителя по реестру | `PersonBureauSource` → `bki_person_http.py` | `POST /bki/person-report` | `bki_head: CreditHistoryDTO` |
| `statement` | прогноз по выпискам клиента (внутренний, не внешний источник) | `StatementParser` → `statement_csv.py`, расчёт — `CashflowBuilder` | — | `cashflow: CashflowForecastDTO` |

Процесс просит все семь (`FetchEnrichment.sources` по умолчанию — тоже все семь). Новые источники
хранятся так же, как старые, — строкой `enrichment_source_results` с JSONB `data`, поэтому миграция
не понадобилась; старые снимки читаются (нет `account_blocks` — блокировок нет).

`EnrichmentSnapshotDTO`, что добавилось:

```text
gir_bo: {
  available: boolean, reason: string | null,          // нет отчётности: ИП, компания младше года
  periods: [{ year, revenue, cost_of_sales, sales_profit, interest_payable, net_profit,
              fixed_assets, inventories, receivables, cash, equity, total_assets,
              long_term_liabilities, short_term_liabilities, total_liabilities }]
} | null                                              // рубли; у источника — тыс. ₽, переводит адаптер
kontur: {
  reliability: "green" | "yellow" | "red", notes: string[],
  arbitration: { as_defendant, as_plaintiff, defendant_sum },
  enforcement: { active, sum },
  bankruptcy_messages: [{ date, type, case }],
  gov_contracts: { count, sum },
  active_pledges
} | null
bki_head: CreditHistoryDTO | null                     // та же схема, что у bki компании
fns.account_blocks: [{ decision_number, date, authority_code, reason }]
sources_skipped: [{ source, code, message }]          // не запрошенные: no_consent, no_head
```

`total_liabilities` — строка 1700, итог пассива (капитал и обязательства), как в форме 0710001.
Периоды ГИР БО — от старых к новым, `AccountingReportsDTO.latest` — последний.

## Ключевые решения («зачем»)

- **БКИ — только при согласии (218-ФЗ).** Команда несёт `bki_consent_at`; нет согласия → источник
  `skipped`, запрос не отправляется. Проверяется в use case до обращения к бюро.
- **БКИ руководителя — только при его личном согласии.** Процесс кладёт в команду руководителя по
  реестру (`head`) и момент его согласия из identity (`head_bki_consent_at`). Нет руководителя →
  `bki_head` `skipped` с кодом `no_head`; есть, но нет согласия → `skipped`, `no_consent`. Мок тоже
  отклоняет запрос без `consent_at` (400). Согласие компании в заявке на руководителя не
  распространяется.
- **Параллельный опрос, частичный результат.** Источники опрашиваются `asyncio.gather`; ошибка
  одного не мешает остальным. Это отражает реальность: внешние системы отвечают по-разному.
- **Ретраи и таймаут в адаптере.** На таймаут и 5xx — до `ENRICHMENT_RETRIES` попыток с задержкой
  0.5 → 1 → 2 с; 404 → «не найдено», прочее — «недоступно». Так в логах видны деградация и ретраи.
- **Идемпотентность по event_id команды.** Повтор той же команды возвращает тот же снимок и
  повторно публикует `EnrichmentCompleted` — ответ дойдёт до процесса, даже если первое событие
  потерялось. `causation_id` ответа = event_id команды.
- **Снимок на момент подачи.** Данные хранятся в снимке, а не дёргаются заново — это аудит и
  воспроизводимость скоринга/решения.

## Кассовый разрыв (прогноз по выпискам)

Если к заявке приложены выписки (`statement_document_ids`), модуль строит объяснимый прогноз без ML
и кладёт его в снимок как `cashflow` (`CashflowForecastDTO`).

- **Выписка — внутренние данные, не внешний источник.** Источник `statement` не попадает ни в
  `sources_ok`, ни в `sources_failed` (они только про внешние источники), даже если он есть в
  `sources` команды. Выписка не распозналась →
  `cashflow = None`, обогащение не падает.
- **Парсер — чистый stdlib.** Формат — ниже в «Формат выписки»; суммы в `Decimal`. Кривой формат →
  понятная `StatementParseError` с номером строки, не 500.
- **Прогноз.** По истории считаем средний чистый поток и помесячную сезонность, строим 3 месяца
  вперёд: `средний поток × сезонность − текущие платежи по кредитам (из БКИ) − платёж по новому
  кредиту`. Баланс идёт нарастающим итогом от нуля; уход в минус = операционного потока не хватает
  на платёж → `gap_detected` с месяцем и суммой разрыва. Сезонность учитываем только при
  положительном среднем потоке: если бизнес в среднем сжигает деньги, прогноз — средний поток без
  «удачных» месяцев прошлого года (иначе индекс сезонности меняет знак и прячет падение).
- **Подтверждение выручки.** Годовой оборот по выписке ≥ 70% заявленной → `revenue_confirmed = True`;
  заявленной выручки нет → `None`. Это сигнал для `decision`, а не самостоятельное решение.

Синтетические выписки демо-компаний (`backend/seed/demo_data.py`) генерирует `scripts/generate_statements.py` в
`seed/statements/<код>.csv` (детерминированно, запуск `uv run python -m scripts.generate_statements`).

## Формат выписки (для фронта)

По этому описанию фронт подсказывает клиенту, что загружать. Выписка прикладывается к заявке как
документ типа `bank_statement`: файл `.csv`, тип `text/csv` (или `application/vnd.ms-excel`), до 20 МБ.
Можно приложить несколько файлов — операции из них объединяются.

- **Кодировка** UTF-8 (BOM допускается), **разделитель** — точка с запятой `;`.
- **Первая строка — заголовок.** Колонки ищутся по названию: порядок любой, лишние игнорируются.
- **Пустые строки** пропускаются; файл только с заголовком — прогноза нет, но это не ошибка.
- **Период:** лучше 6–12 месяцев. Сезонность считается по календарным месяцам, дозапрос банка
  просит выписку «за 6 месяцев».

| Колонка | Обязательна | Формат | Пример |
|---|---|---|---|
| `date` | да | дата операции `ГГГГ-ММ-ДД` | `2026-01-05` |
| `amount` | да | сумма в рублях: десятичная **точка**, без пробелов и валюты; `> 0` — поступление, `< 0` — списание | `150000.00`, `-48000.00` |
| `counterparty_inn` | нет | ИНН контрагента | `7701234567` |
| `counterparty_name` | нет | наименование контрагента | `ООО Поставщик` |
| `purpose` | нет | назначение платежа | `Оплата по счёту 12` |

```
date;amount;counterparty_inn;counterparty_name;purpose
2026-01-05;150000.00;7701234567;ООО Поставщик;Оплата по счёту 12
2026-01-06;-48000.00;7709876543;ООО Аренда;Аренда за январь
2026-01-15;-120000.00;;Зарплата сотрудникам;Выплата зарплаты
```

**Что считается ошибкой** (выписка не распознана — прогноз не строится, `cashflow = None`, заявка
идёт дальше без прогноза): нет колонок `date` или `amount`; дата не в формате `ГГГГ-ММ-ДД`; сумма с
запятой (`1500,00`), пробелами (`1 500.00`) или знаком валюты. Текст ошибки содержит номер строки —
его можно показать клиенту.

## События

- Слушает `enrichment.commands` → `FetchEnrichment {application_id, organization_id, inn, sources,
  bki_consent_at, statement_document_ids, head, head_bki_consent_at}` (group `enrichment.commands`).
  `head {account_id, last_name, first_name, middle_name}` — руководитель по реестру,
  `head_bki_consent_at` — момент его личного согласия на запрос своей кредитной истории (identity,
  `/me/consents`); без согласия — `null`. Оба поля необязательные: старые команды читаются.
- Публикует `enrichment.events` → `EnrichmentCompleted {application_id, snapshot_id, sources_ok,
  sources_failed, cash_gap_detected}` (`cash_gap_detected = None`, если выписок не было) — если
  ответил хотя бы один внешний источник (частичный результат — нормальный исход).
- Публикует `EnrichmentFailed {application_id, reason}`, если не ответил **ни один** внешний источник
  (например, нет сети до моков): считать не на чем, process решает по `on_failure`. Снимок с ошибками
  всё равно сохраняется для аудита; `reason` — `all_sources_failed: egrul=unavailable, fns=timeout,
  bki=no_consent, gir_bo=…, kontur=…, bki_head=no_head`. Повтор команды повторяет тот же ответ.

## Фасад

- `get_snapshot(application_id)` — последний снимок для `scoring`, `decision`, карточки андеррайтера
  (bff).
- `lookup_registry(inn, *, fresh=False)` — только ЕГРЮЛ, кеш в памяти 10 минут; `fresh=True` идёт
  мимо кеша (сверка компании по запросу в clients) и обновляет его. Не найдено → `None`; реестр
  недоступен → `InfrastructureError` (503).
- В выписке `RegistryExtractDTO` есть `kpp` (`None` у ИП и в снимках, сохранённых до него).

## Моки (для README и `THIRD_PARTY_NOTICES`)

Все внешние источники — смоделированы сервисом `external-mocks` (ЕГРЮЛ/ЕГРИП, ФНС, ГИР БО,
Контур, БКИ компании и физлица). Настоящих
реестров и платных API нет. Настройки — блок `# --- enrichment ---` в `.env.example`.

В `docker-compose.yml` моки — отдельный сервис `external-mocks` (порт 8100 внутри сети, наружу не
открыт); backend ждёт его healthcheck и ходит по `ENRICHMENT_MOCKS_BASE_URL=http://external-mocks:8100`.
Для демо «хаос» выключен: задержка 100–400 мс, без случайных 503 (`MOCK_FAILURE_RATE=0`); чтобы
показать устойчивость к сбоям, поднимите `MOCK_FAILURE_RATE`, например до `0.1`. БКИ «Сбоя»
(`7705729405`) отвечает 503 всегда — сценарий S-6; так же и отчёт по его руководителю.

Сценарии новых источников для демо-компаний: у «Заката» блокировка счёта, отрицательный капитал
в последнем году, исполнительные производства и иски больше порогов, у его руководителя — текущая
просрочка 45 дней; у «Прогресса» выручка ГИР БО совпадает с ФНС (12 млн против заявленных 36);
у ИП Иванова отчётности в ГИР БО нет. Остальные ИНН — детерминированная генерация.

## Упрощения

- Прогноз кассового разрыва — оценочный: аннуитет по новому кредиту и помесячная сезонность
  считаются грубо на демо-данных; для продакшена нужна калибровка на реальных выписках.
- Сезонность при годовой истории повторяет прошлогодние месяцы и не учитывает тренд внутри года:
  для падающего бизнеса с ещё положительным средним потоком прогноз оптимистичен. Для бизнеса с
  отрицательным средним потоком сезонность отключена (см. «Прогноз»).
- Сырые ответы источников (`raw`) не сохраняются (мапим сразу в DTO) — это «Should», можно добавить
  отдельной колонкой для аудита.
