import type {
  ApplicationStatusCode,
  BeneficialOwnerInput,
  BeneficialOwnersDto,
  BeneficiaryDto,
  BusinessPlanDto,
  ClientStatus,
  ConsentsDto,
  FounderPrescreenDto,
  OrganizationDetailDto,
  OrganizationSummaryDto,
  PreApprovedOfferDto,
  ProductDto,
  ProjectAssessmentDto,
  SupportTicketDto,
  SupportTicketListItemDto,
  SupportTicketStatus,
  ThirdPartyDto,
} from '../client/types'
import type { DownloadedFile } from '../http'

/**
 * Бэк-офис андеррайтера на бэкенде (docs/api/client-journey.md §3.8): очередь задач,
 * карточка заявки с источниками, скорингом и правилами решения, решение по задаче, метрики.
 * Поля — как в openapi.json; здесь только то, что показывает рабочее место.
 */

/** Вид ручной проверки (policy_v5): check — проверка, dispute — спорная (модели или данные расходятся) */
export type ReviewKind = 'check' | 'dispute'

export type Grade = 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G' | 'H' | 'I' | 'J'

export interface QueueItemDto {
  task_id: string
  application_id: string
  number: string
  company_name: string
  inn: string
  product_code: string
  amount: string | null
  /** Балл и грейд PD-модели, A–J */
  score: number | null
  risk_grade: string | null
  /** По выпискам ожидается кассовый разрыв */
  cash_gap: boolean
  /** Почему заявка ушла на ручную проверку: ROUTE_* */
  routing_reasons: string[]
  review?: ReviewKind | null
  due_at: string | null
  overdue: boolean
  assignee_id: string | null
  /** open | in_progress | done | cancelled */
  status: string
  created_at: string
}

/** Заявка в списке всех заявок сотрудника (GET /applications): и черновики, и решённые автоматикой */
export interface StaffApplicationDto {
  id: string
  number: string
  organization_id: string
  product_code: string
  status: ApplicationStatusCode
  client_stage: string | null
  amount: string | null
  term_months: number | null
  updated_at: string
  submitted_at: string | null
}

/** Фильтры GET /applications: status повторяется в query, decided_by — кто решил; limit до 100 */
export interface StaffApplicationsQuery {
  organizationId?: string
  status?: ApplicationStatusCode[]
  decidedBy?: 'auto' | 'underwriter'
  limit?: number
  offset?: number
}

export interface QueuePageDto {
  items: QueueItemDto[]
  total: number
}

export interface FinancialReportSnapshotDto {
  period_year: number
  period_quarter: number | null
  source: 'declared' | 'fns' | 'bank_statement'
  revenue: string
  expenses: string | null
  net_profit: string | null
  total_liabilities: string | null
  monthly_debt_payments: string | null
}

export interface UnderwriterApplicationDto {
  id: string
  number: string
  organization_id: string
  product_code: string
  product_terms: {
    code: string
    amount_min: string
    amount_max: string
    term_min_months: number
    term_max_months: number
    rate_base: string
    rate_max: string
    auto_decision_limit: string
    /** Маршрут продукта: по нему схема строится ещё до процесса — у черновика */
    workflow_code?: string
  }
  request: { amount: string; term_months: number; purpose: string; purpose_comment: string | null } | null
  product_fields: Record<string, unknown>
  collateral: { type: string; description: string; declared_value: string; owner: string; owner_party?: ThirdPartyDto | null } | null
  /** Ответ клиента о третьем лице (выгодоприобретателе); null — не ответил */
  beneficiary?: BeneficiaryDto | null
  /** Бенефициары со слов клиента (115-ФЗ); null — не ответил */
  beneficial_owners?: BeneficialOwnersDto | null
  /** Согласия заявки: когда даны и откуда — галочка в черновике или из профиля */
  consents?: (ConsentsDto & { given_by?: string | null }) | null
  org_snapshot: {
    inn: string
    ogrn: string
    kpp: string | null
    legal_form: string
    name: string
    registered_at: string
    business_age_months: number
    okved_main: string
    tax_regime: string
    employees_count: number
    /** active | liquidating | liquidated | bankrupt | reorganizing | excluded */
    registry_status: string
    verification_status: 'unverified' | 'verified' | 'mismatch'
    discrepancies: { field: string; declared: string | null; registry: string | null }[]
    head_name: string | null
    financial_reports: FinancialReportSnapshotDto[]
  } | null
  status: ApplicationStatusCode
  client_stage: string | null
  documents: { id: string; type: string; filename: string; status: string; uploaded_at: string | null; review_comment: string | null }[]
  info_requests: { id: string; requested_documents: string[]; comment: string; status: string; created_at: string; answered_at: string | null }[]
  offer: { kind: string; amount: string; term_months: number; rate: string; monthly_payment: string; conditions: string[]; expires_at: string } | null
  submitted_at: string | null
  created_at: string
}

export interface ObligationDto {
  creditor: string
  kind: string
  amount: string
  balance: string
  monthly_payment: string
  opened_at: string
  closes_at: string | null
  overdue_days: number
}

export type EnrichmentSource =
  | 'egrul'
  | 'fns'
  | 'bki'
  | 'statement'
  | 'gir_bo'
  | 'kontur'
  | 'bki_head'
  | 'aml'
  | 'bank_stop_list'
  | 'bank_turnover'

export interface SourceErrorDto {
  source: EnrichmentSource
  code: string
  message: string
}

export interface CreditHistoryDto {
  obligations: ObligationDto[]
  inquiries_last_30d: number
  has_active_overdue: boolean
  max_overdue_days_12m: number
  total_monthly_payments: string
}

/** Бухотчётность из ГИР БО за год */
export interface AccountingPeriodDto {
  year: number
  revenue: string
  net_profit: string
  equity: string
  total_assets: string
  total_liabilities: string
  receivables: string
  cash: string
}

/** Контур: надёжность, суды, приставы, банкротство, госконтракты */
export interface CounterpartyRiskDto {
  reliability: 'green' | 'yellow' | 'red'
  notes: string[]
  arbitration: { as_defendant: number; as_plaintiff: number; defendant_sum: string }
  enforcement: { active: number; sum: string }
  bankruptcy_messages: { date: string; type: string; case: string }[]
  gov_contracts: { count: number; sum: string }
  active_pledges: number
}

/**
 * Кого проверили по 115-ФЗ: компания, учредитель-юрлицо цепочки, руководитель, бенефициар, представитель,
 * выгодоприобретатель и залогодатель — третье лицо
 */
export interface AmlSubjectDto {
  /** founder — учредитель-физлицо с любой долей, declared_owner — бенефициар со слов клиента (policy_v9) */
  role:
    | 'company'
    | 'founder_company'
    | 'head'
    | 'beneficial_owner'
    | 'representative'
    | 'beneficiary'
    | 'pledgor'
    | 'founder'
    | 'declared_owner'
  name: string
  inn: string | null
  /** Страна: у учредителей — из ЕГРЮЛ, у третьих лиц и названных бенефициаров — со слов клиента */
  country?: string | null
}

/** Проверка по 115-ФЗ: бенефициары, перечни Росфинмониторинга, публичные должностные лица, риск ЗСК */
export interface AmlCheckDto {
  lists_date: string
  zsk: { level: 'low' | 'medium' | 'high'; as_of: string }
  beneficial_owners: { name: string; basis: 'ownership' | 'head_by_default' | 'entrepreneur'; share_percent: string | null }[]
  subjects: AmlSubjectDto[]
  list_hits: { subject: AmlSubjectDto; list: 'terrorism' | 'freeze' | 'wmd'; record: string }[]
  pep_hits: { subject: AmlSubjectDto; kind: 'foreign' | 'russian' | 'international'; position: string }[]
  /** Бенефициары со слов клиента; null — клиент не ответил */
  declared_owners?: (BeneficialOwnerInput & { country: string | null })[] | null
  /** Сверка с ЕГРЮЛ: not_declared — клиент не назвал владельца по реестру, not_in_registry — назвал, а в реестре его нет */
  owner_discrepancies?: { name: string; kind: 'not_declared' | 'not_in_registry' }[]
  /** Действующие лицензии (ст. 7 п. 15 115-ФЗ); null — реестр лицензий не ответил */
  licenses?: { number: string; activity: string; okved: string }[] | null
}

/** Обороты по расчётному счёту в банке (АБС) за 24 месяца */
export interface BankTurnoverDto {
  client_since: string | null
  months: { month: string; inflow: string; outflow: string }[]
}

export interface EnrichmentDto {
  collected_at: string
  sources_ok: EnrichmentSource[]
  sources_failed: SourceErrorDto[]
  /** Не запрошены: БКИ — нет согласия, БКИ руководителя — нет согласия или руководителя */
  sources_skipped?: SourceErrorDto[]
  egrul: {
    full_name: string
    status: string
    registered_at: string
    okved_main: string
    head_last_name: string
    head_first_name: string
    head_middle_name: string | null
    head_position: string
    founders: { name: string; share_percent: string; inn?: string | null; country?: string | null }[]
    address: string
    mass_address: boolean
    kpp?: string | null
    /** С какой даты руководитель в реестре */
    head_since?: string | null
    /** Отметки о недостоверности сведений: адрес, руководитель, учредитель */
    unreliable?: ('address' | 'head' | 'founder')[]
  } | null
  fns: {
    tax_arrears: string
    avg_headcount: number
    reported_revenue: string | null
    report_year: number | null
    tax_regime: string
    disqualified_head: boolean
    in_msp_registry: boolean
    /** Приостановления операций по счетам */
    account_blocks?: { decision_number: string; date: string; authority_code: string; reason: string }[]
    /** Признаки массового руководителя */
    mass_head?: boolean | null
  } | null
  bki: CreditHistoryDto | null
  /** БКИ руководителя — только с его личным согласием */
  bki_head?: CreditHistoryDto | null
  gir_bo?: { available: boolean; reason: string | null; periods: AccountingPeriodDto[] } | null
  kontur?: CounterpartyRiskDto | null
  /** Проверка по 115-ФЗ; null — не выполнена (aml в sources_failed) */
  aml?: AmlCheckDto | null
  /** Внутренний стоп-лист банка */
  bank_stop_list?: { listed: boolean; reason: string | null; listed_at: string | null } | null
  bank_turnover?: BankTurnoverDto | null
  cashflow: {
    months_history: { month: string; inflow: string; outflow: string; net: string; balance: string }[]
    forecast: { month: string; projected_balance: string }[]
    gap_detected: boolean
    gap_month: string | null
    gap_amount: string | null
    annual_inflow: string
    revenue_confirmed: boolean | null
  } | null
}

export interface FactorDto {
  code: string
  value: string | null
  bin: string
  points: number
  direction: 'positive' | 'negative' | 'neutral'
  client_hint: string | null
}

/** Оценка ML-модели на тех же данных и той же шкале A–J, что у PD-модели */
export interface MlScoreDto {
  model_version: string
  /** Вероятность дефолта за 12 месяцев, доля */
  pd_12m: string
  score: number
  grade: Grade
  factors: FactorDto[]
  reason_codes: string[]
}

export interface ScoringDto {
  model_version: string
  score: number
  grade: Grade
  factors: FactorDto[]
  flags: string[]
  data_completeness: string
  computed_at: string
  segment?: 'legal_entity' | 'entrepreneur' | 'new_client' | null
  scorecard?: string | null
  /** Вероятность дефолта за 12 месяцев, доля */
  pd_12m?: string | null
  /** Факторы, сильнее всего снизившие балл */
  reason_codes?: string[]
  /** Оценка ML-модели; нет — заявка оценена до появления второй модели или модель не применяется */
  ml?: MlScoreDto | null
  /** no_revenue — у компании нет выручки ни в заявке, ни по ФНС: ML-модель на таких не обучена и не оценивает */
  ml_not_applicable?: 'no_revenue' | null
  /** Данные полные? degraded — не ответил критичный источник или мало признаков: решает человек */
  quality?: 'ok' | 'degraded' | null
  /** source_failed:<источник>, completeness_below:<доля> */
  quality_reasons?: string[]
}

/** Лимиты движка; binding — какой из них дал итоговый минимум */
export interface LimitsDto {
  by_revenue: string | null
  by_ltv: string | null
  by_capacity: string | null
  by_product?: string | null
  by_turnover?: string | null
  by_grade?: string | null
  by_group?: string | null
  final?: string | null
  binding?: string | null
}

export interface DecisionDto {
  policy_version: string
  key_rate: string
  outcome: 'APPROVE' | 'COUNTER_OFFER' | 'REQUEST_INFO' | 'MANUAL_REVIEW' | 'REJECT'
  terms: { amount: string; term_months: number; rate: string; monthly_payment: string; conditions: string[] } | null
  alternative_product_code: string | null
  reason_codes: string[]
  client_explanation: string
  rule_trace: { rule: string; matched: boolean; detail: string }[]
  limits: LimitsDto
  decided_by_type: 'auto' | 'underwriter'
  comment: string | null
  decided_at: string
  /** Мягкие триггеры, из-за которых заявка ушла на ручную проверку */
  triggers?: { code: string; detail: string }[]
  /** Из чего сложилась ставка, процентные пункты */
  rate_breakdown?: { funding: string; expected_loss: string; capital: string; margin: string; total: string } | null
  /** Вид ручной проверки — только у MANUAL_REVIEW */
  review?: ReviewKind | null
}

export interface UnderwriterTaskDto {
  id: string
  type: string
  candidate_role: string
  assignee_id: string | null
  /** open | in_progress | done | cancelled */
  status: string
  created_at: string
  due_at: string | null
  result: Record<string, unknown> | null
}

/** Карточка андеррайтера (GET /bff/backoffice/applications/{id}) */
export interface UnderwriterCardDto {
  application: UnderwriterApplicationDto
  client_status: ClientStatus
  enrichment: EnrichmentDto | null
  scoring: ScoringDto | null
  decision: DecisionDto | null
  product_fit: { eligible: boolean; reasons: { code: string; passed: boolean; message: string }[] } | null
  timeline: { id: string; at: string; kind: string; title: string; audience: 'client' | 'bank' }[]
  process: {
    workflow_code: string
    status: string
    client_stage: string | null
    steps: { node_id: string; step_code: string | null; kind: string; started_at: string; finished_at: string | null; outcome: string | null; error: string | null }[]
  } | null
  task: UnderwriterTaskDto | null
  degraded: string[]
  /** Заявка стартапа с проектной оценкой её продукта */
  startup?: StartupProjectDto | null
}

/** Проектная оценка стартапа для андеррайтера — с цифрами модели, которых клиент не видит */
export interface ProjectAssessmentFullDto extends ProjectAssessmentDto {
  figures: {
    requested_amount: string
    term_months: number
    rate: string
    cash_flow: string
    debt_service: string
    dscr: string | null
    own_share: string
    coverage: string
    /** Сколько выдерживает проект */
    capacity: string
  }
  version: string
}

/** С чем открыть форму проектной оценки: андеррайтер подтверждает или правит */
export interface ProjectFormDto {
  decision: 'approve' | 'counter_offer' | 'reject'
  amount: string | null
  term_months: number | null
  business_plan: 'strong' | 'acceptable' | 'weak'
  collateral: string | null
  support_program: boolean
}

export interface StartupProjectDto {
  assessment: ProjectAssessmentFullDto
  business_plan: BusinessPlanDto | null
  /** План уточнили после оценки */
  plan_changed: boolean
  /** Оценка действовала на дату подачи */
  valid_at_submission: boolean
  form: ProjectFormDto
}

/** Состояние процесса: running — идёт, waiting — ждёт человека или внешний сервис, остальные — финал */
export type ProcessStatus = 'running' | 'waiting' | 'completed' | 'failed' | 'cancelled'

/** Шаг процесса — один проход узла BPMN; узел, пройденный дважды, даёт два шага с iteration 1 и 2 */
export interface ProcessStepDto {
  node_id: string
  step_code: string | null
  /** immediate — выполнен сразу, async — ждёт внешний сервис, stoppable — ждёт человека */
  kind: 'immediate' | 'async' | 'stoppable'
  iteration: number
  started_at: string
  finished_at: string | null
  /** completed | failed | cancelled; null — шаг ещё идёт */
  outcome: string | null
  client_stage: string | null
  error: string | null
}

/** Где заявка на маршруте банка (GET /processes/{application_id}) */
export interface ProcessDto {
  process_id: string
  application_id: string
  /** Код маршрута: схема — GET /workflows/{code}/diagram */
  workflow_code: string
  workflow_version: number
  status: ProcessStatus
  /** Узел, на котором процесс сейчас; у завершённого — null */
  current_node_id: string | null
  client_stage: string | null
  /** Пройденные узлы без повторов, в порядке первого прохода */
  visited_node_ids: string[]
  /** Шаги по времени, с повторами */
  steps: ProcessStepDto[]
  started_at: string
  finished_at: string | null
}

export interface MetricsDto {
  date_from: string
  date_to: string
  rows: {
    day: string
    product_code: string
    submitted: number
    approved: number
    counter_offers: number
    rejected: number
    manual_reviews: number
    auto_decisions: number
    avg_time_to_decision_sec: number | null
  }[]
  submitted: number
  decided: number
  auto_decision_share: number | null
  avg_time_to_decision_sec: number | null
}

export type TaskDecision = 'approve' | 'counter_offer' | 'reject' | 'request_info'

export interface TaskResultInput {
  decision: TaskDecision
  amount?: number | null
  term_months?: number | null
  rate?: number | null
  conditions: string[]
  requested_documents: string[]
  comment: string
  /** Только проектная оценка стартапа */
  business_plan?: ProjectFormDto['business_plan']
  collateral?: string | null
  support_program?: boolean
}

/* ---------- Ведение каталога продуктов (PR #200, docs/modules/products.md) ---------- */

/** Условия продукта для PUT /products/{code}: карточка из GET без code, version и status */
export type ProductInput = Omit<ProductDto, 'code' | 'version' | 'status'>

/** Новый продукт: версия 1 в конце каталога, черновик или сразу в продаже */
export interface ProductCreateInput extends ProductInput {
  code: string
  status: 'draft' | 'active'
}

/** BPMN-маршрут процесса — для выбора workflow_code продукта */
export interface WorkflowDto {
  code: string
  version: number
  source_hash: string
  nodes: number
  flows: number
}

/* ---------- Проверка компании по ИНН до заявки (POST /organizations/inn-check, #213) ---------- */

export type InnCheckVerdict = 'ok' | 'warning' | 'fail' | 'not_found'
export type InnCheckStatus = 'passed' | 'warning' | 'failed' | 'skipped'
/** input — сверка с реквизитами из документов клиента, bank — данные банка */
export type InnCheckSource = 'input' | 'egrul' | 'fns' | 'kontur' | 'bank'

/** ИНН и, если клиент их назвал, реквизиты из его документов: ИНН сверяется с каждым переданным */
export interface InnCheckInput {
  inn: string
  ogrn?: string
  kpp?: string
  name?: string
}

export interface InnCheckDto {
  inn: string
  /** Худший статус проверок: failed — fail; warning или источник не ответил — warning */
  verdict: InnCheckVerdict
  /** Итог словами */
  summary: string
  checked_at: string
  checks: { code: string; title: string; status: InnCheckStatus; message: string; source: InnCheckSource }[]
  /** ЕГРЮЛ / ЕГРИП; null — ИНН не найден или с ошибкой в контрольной цифре */
  company: {
    inn: string
    ogrn: string
    kpp: string | null
    legal_form: 'LLC' | 'IE' | 'JSC'
    name: string
    full_name: string
    registry_status: 'active' | 'liquidating' | 'liquidated' | 'bankrupt' | 'reorganizing' | 'excluded'
    registered_at: string
    address: { full: string; region_code: string }
    mass_address: boolean
    unreliable: ('address' | 'head' | 'founder')[]
    okved_main: string
    okved_extra: string[]
    head_name: string
    head_position: string
    head_since: string | null
    founders: { name: string; share_percent: string; inn: string | null }[]
  } | null
  /** ФНС; null — не ответила */
  tax: {
    tax_regime: string
    avg_headcount: number
    reported_revenue: string | null
    report_year: number | null
    tax_arrears: string
    in_msp_registry: boolean
    disqualified_head: boolean
    mass_head: boolean | null
    account_blocks: { decision_number: string; date: string; reason: string }[]
  } | null
  /** Контур; null — не ответил */
  counterparty: {
    reliability: 'green' | 'yellow' | 'red'
    notes: string[]
    arbitration_as_defendant: number
    arbitration_defendant_sum: string
    enforcement_active: number
    enforcement_sum: string
    bankruptcy_messages: { date: string; type: string; case: string }[]
  } | null
  /** Компания — клиент банка: её карточка */
  organization_id: string | null
}

/** Порядок очереди: срок по SLA, сумма, балл скоринга, создана */
export type QueueSort = 'due_at' | 'amount' | 'score' | 'created_at'

export interface BackofficeApi {
  /** limit до 100; total — сколько задач всего с этим статусом */
  queue(query?: { status?: string; sort?: QueueSort; limit?: number; offset?: number }): Promise<QueuePageDto>
  card(applicationId: string): Promise<UnderwriterCardDto>
  /** Взять задачу на себя */
  claim(taskId: string): Promise<UnderwriterTaskDto>
  /** Решение по задаче: одобрить, контрпредложение, отказ, запрос информации */
  complete(taskId: string, input: TaskResultInput): Promise<UnderwriterTaskDto>
  metrics(query?: { dateFrom?: string; dateTo?: string }): Promise<MetricsDto>
  downloadDocument(applicationId: string, documentId: string): Promise<{ url: string }>
  /** PDF договора — банк видит договоры всех заявок; kind не задан — последний готовый */
  contractDocument(applicationId: string, kind?: 'draft' | 'signed'): Promise<DownloadedFile>
  /** Процесс заявки: текущий узел и пройденные шаги */
  process(applicationId: string): Promise<ProcessDto>
  /** Схема маршрута — BPMN 2.0 XML */
  workflowDiagram(code: string): Promise<string>
  /** Все заявки, свежие сверху; сотруднику — всех компаний, со статусом, этапом и черновиками */
  applications(query?: StaffApplicationsQuery): Promise<StaffApplicationDto[]>
  /** Сотрудник видит все компании банка */
  organizations(): Promise<OrganizationSummaryDto[]>
  organization(organizationId: string): Promise<OrganizationDetailDto>
  /** До заявки — предскоринг компании: предодобренные предложения, у стартапа — проверка учредителя и проектная оценка */
  preApprovedOffers(organizationId: string): Promise<PreApprovedOfferDto[]>
  /** 404 — проверки не было */
  founderPrescreen(organizationId: string): Promise<FounderPrescreenDto>
  /** 404 — оценки не было */
  projectAssessment(organizationId: string): Promise<ProjectAssessmentDto>
  /** Бизнес-план стартапа; 404 — ещё не загружен */
  businessPlan(organizationId: string): Promise<BusinessPlanDto>
  /**
   * all — для ведения каталога: последняя версия каждого продукта, с черновиками и архивом (нужно credits.update);
   * active — продукты в продаже, как на сайте
   */
  products(scope: 'all' | 'active'): Promise<ProductDto[]>
  /** 409 — код занят; 422 — неизвестный маршрут или занятая карточка frontend_id */
  createProduct(input: ProductCreateInput): Promise<ProductDto>
  /** Черновик правится на месте, у продукта в продаже — новая версия; снятый с продажи этим же возвращается */
  updateProduct(code: string, input: ProductInput): Promise<ProductDto>
  /** Выпустить черновик в продажу */
  activateProduct(code: string): Promise<ProductDto>
  /** Снять с продажи: продукт уходит в архив, черновик удаляется */
  withdrawProduct(code: string): Promise<void>
  workflows(): Promise<WorkflowDto[]>
  /** Проверка по ИНН до заявки, только для банка (backoffice.read); реестр не ответил — 503 */
  innCheck(input: InnCheckInput): Promise<InnCheckDto>
  /** Очередь обращений: all — все, unassigned — никто не взял, mine — взятые мной */
  supportQueue(query?: {
    status?: SupportTicketStatus[]
    scope?: 'all' | 'unassigned' | 'mine'
    limit?: number
    offset?: number
  }): Promise<SupportTicketListItemDto[]>
  supportTicket(id: string): Promise<SupportTicketDto>
  /** Уже взято — 409 already_taken, кто взял — в details.assignee_id */
  takeSupportTicket(id: string): Promise<SupportTicketDto>
  /** Вернуть в очередь: исполнитель или админ */
  releaseSupportTicket(id: string): Promise<SupportTicketDto>
  /** Не взято — 409 not_taken, взял другой — 403 not_assignee */
  replySupportTicket(id: string, text: string): Promise<SupportTicketDto>
  resolveSupportTicket(id: string): Promise<SupportTicketDto>
  closeSupportTicketByStaff(id: string): Promise<SupportTicketDto>
  /** Версии PD-модели: читать и примерять — scoring.read, вести — scoring.update */
  scoringModels: VersionsApi<ModelCatalogDto, ModelPreviewDto>
  /** Версии кредитной политики: права те же, что у версий PD-модели */
  decisionPolicies: VersionsApi<PolicyCatalogDto, PolicyPreviewDto>
}

/**
 * Версии PD-модели (/scoring/models) и кредитной политики (/decision/policies) устроены одинаково:
 * встроенная версия из YAML только читается, версии админа — `<встроенная>.<n>`, draft → active → archived.
 * Черновик — копия любой версии; править и удалять можно только его. Активировать черновик или архивную —
 * это и откат; активировать встроенную — вернуть YAML (docs/modules/scoring.md, decision.md)
 */
export type VersionStatus = 'draft' | 'active' | 'archived'

export interface VersionSummaryDto {
  version: string
  status: VersionStatus
  builtin: boolean
  based_on: string | null
  comment: string | null
  created_by: string | null
  created_at: string | null
  updated_at: string | null
  activated_by: string | null
  activated_at: string | null
}

/** Документ версии — тот же YAML в JSON: Decimal строками, пустые поля опущены */
export type VersionBody = Record<string, unknown>

export interface VersionDto extends VersionSummaryDto {
  body: VersionBody
}

/** Ошибка документа из 422 (details.errors): путь в документе и текст */
export interface VersionBodyError {
  path: string
  message: string
}

export interface VersionsApi<Catalog, Preview> {
  /** Встроенная первой, затем версии админа; без body */
  list(): Promise<VersionSummaryDto[]>
  /** Из чего собирается документ */
  catalog(): Promise<Catalog>
  get(version: string): Promise<VersionDto>
  /** Черновик-копия версии based_on; нет такой — 404 */
  createDraft(input: { based_on: string; comment?: string }): Promise<VersionDto>
  /** Документ целиком; comment не прислали — остаётся прежний. 422 — details.errors, 409 — не черновик */
  updateDraft(version: string, input: { body: VersionBody; comment?: string }): Promise<VersionDto>
  /** Только черновик, иначе 409 */
  deleteDraft(version: string): Promise<void>
  /** Черновик или архивная → активная; встроенная — вернуть YAML. Уже активна — 409 */
  activate(version: string): Promise<VersionDto>
  /** Пересчитать последние заявки версией-кандидатом, ничего не пишет; limit 1–500 */
  preview(version: string, limit?: number): Promise<Preview>
}

export interface ModelFeatureInfoDto {
  code: string
  /** numeric — интервальные бины [from; to), categorical — бины категорий */
  kind: 'numeric' | 'categorical'
  /** Категории, у каждой из которых обязан быть бин */
  categories: string[]
  /** Обязателен в скоркарте каждого сегмента */
  required: boolean
}

export interface ModelCatalogDto {
  builtin: string
  segments: string[]
  features: ModelFeatureInfoDto[]
  /** Грейды с верхней границей PD, по возрастанию */
  grades: Grade[]
  /** PD выше границы последнего грейда */
  worst_grade: Grade
  industry_sections: string[]
}

export interface CodeNameDto {
  code: string
  name: string
}

export interface PolicyReasonDto {
  code: string
  /** Что клиент увидит в решении */
  text: string
  hint: string | null
}

export interface PolicyCatalogDto {
  builtin: string
  legacy_scale: Grade[]
  pd_scale: Grade[]
  outcomes: CodeNameDto[]
  /** Коды причин с текстами для клиента; код без текста в документе — 422 */
  reasons: PolicyReasonDto[]
  stop_factors: string[]
  registry_statuses: string[]
  routing_flags: string[]
  zones: string[]
  zone_verdicts: string[]
  zsk_levels: string[]
  legal_forms: string[]
  collateral_types: CodeNameDto[]
  products: CodeNameDto[]
}

export interface VersionShiftDto {
  from: string
  to: string
  count: number
}

export interface ModelEstimateDto {
  score: number
  pd_12m: string | null
  grade: Grade
  segment: string | null
  model_version: string
}

export interface ModelPreviewItemDto {
  application_id: string
  result_id: string
  computed_at: string
  /** Как посчитано тогда своей версией модели */
  before: ModelEstimateDto
  /** Как посчитала бы примеряемая версия */
  after: ModelEstimateDto
}

export interface ModelPreviewDto {
  version: string
  total: number
  same: number
  better: number
  worse: number
  /** Снимок входа не прочитан */
  skipped: number
  /** Переходы грейдов, только непустые */
  transitions: VersionShiftDto[]
  items: ModelPreviewItemDto[]
}

export interface PolicyVerdictDto {
  outcome: 'APPROVE' | 'COUNTER_OFFER' | 'REQUEST_INFO' | 'MANUAL_REVIEW' | 'REJECT'
  reason_codes: string[]
  policy_version: string
}

export interface PolicyPreviewItemDto {
  application_id: string
  /** Сохранённое автоматическое решение */
  result_id: string
  decided_at: string
  before: PolicyVerdictDto
  /** Как решила бы примеряемая версия на текущих данных заявки */
  after: PolicyVerdictDto
}

export interface PolicyPreviewDto {
  version: string
  total: number
  /** Другой исход или другие коды причин */
  changed: number
  outcome_changed: number
  /** Вход не собрать: заявки или продукта уже нет */
  skipped: number
  /** Переходы исходов, только непустые */
  transitions: VersionShiftDto[]
  items: PolicyPreviewItemDto[]
}
