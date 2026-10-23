import type { MeDto, TokenResponse } from '../identity/types'

/**
 * Клиентский путь сайта: вход клиента, каталог, калькулятор, компании и заявка.
 * Схемы — из docs/api/openapi.json, правила — docs/api/client-journey.md.
 * Поля в snake_case, деньги и ставки — десятичные строки, как их отдаёт бэкенд.
 * Запросы подписываются токеном клиента, а не сотрудника: у сайта своя сессия.
 */

/** Демо-учётка для входа одной кнопкой (GET /auth/demo-accounts) */
export interface DemoAccountDto {
  /** Email, который передаётся в POST /auth/demo-login */
  login: string
  phone: string | null
  /** client | underwriter */
  role: string
  caption: string
  full_name: string
}

export type LoanPurpose =
  | 'working_capital'
  | 'cash_gap'
  | 'equipment'
  | 'vehicles'
  | 'real_estate'
  | 'contract_execution'
  | 'refinancing'
  | 'expansion'

export type Facility = 'term_loan' | 'credit_line_revolving' | 'credit_line_non_revolving' | 'overdraft'

export type Repayment = 'annuity' | 'differentiated' | 'interest_only' | 'by_contract_schedule'

export type CollateralKind = 'none' | 'optional' | 'required'

export type CollateralType = 'real_estate' | 'equipment' | 'vehicle' | 'goods'

export type LegalForm = 'LLC' | 'IE' | 'JSC'

export interface RequiredDocumentDto {
  type: string
  title: string
  /** Нужен только начиная с этой суммы; null — всегда */
  required_from_amount: string | null
  /** Для каких форм бизнеса; пусто — для всех */
  legal_forms: string[]
}

/** JSON Schema дополнительных полей заявки продукта (product_fields) */
export interface FieldsSchema {
  type?: 'object'
  properties?: Record<string, FieldSchema>
  required?: string[]
}

export interface FieldSchema {
  type?: 'string' | 'number' | 'integer' | 'boolean' | 'array' | 'object'
  title?: string
  enum?: string[]
  minLength?: number
  maxLength?: number
  minimum?: number
  maximum?: number
  minItems?: number
  maxItems?: number
  items?: FieldsSchema
}

export interface ProductDto {
  code: string
  frontend_id: string
  version: number
  name: string
  short_description: string
  description_plain: string
  purposes: LoanPurpose[]
  facility: Facility
  repayment_options: Repayment[]
  amount_min: string
  amount_max: string
  term_min_months: number
  term_max_months: number
  rate_base: string
  rate_max: string
  collateral_kind: CollateralKind
  collateral_required_from: string | null
  collateral_types: string[]
  guarantee: 'none' | 'owner' | 'msp_corporation'
  min_business_age_months: number
  allowed_legal_forms: string[]
  min_annual_revenue: string | null
  required_documents: RequiredDocumentDto[]
  application_fields_schema: FieldsSchema
  auto_decision_limit: string
  status: 'draft' | 'active' | 'archived'
}

export interface CalculateInput {
  amount: number
  term_months: number
  /** Без ставки берётся базовая ставка продукта */
  rate?: number | null
  repayment?: Repayment | null
}

export interface PaymentDto {
  number: number
  due_date: string | null
  principal: string
  interest: string
  total: string
  balance_after: string
}

export interface PaymentScheduleDto {
  amount: string
  term_months: number
  rate: string
  repayment: Repayment
  monthly_payment: string
  total_interest: string
  total_paid: string
  payments: PaymentDto[]
}

/** Одно условие продукта для компании: форма бизнеса, возраст, выручка. message — по-русски */
export interface EligibilityReasonDto {
  code: string
  passed: boolean
  message: string
}

/** Подходит ли компания под продукт (GET /products/{code}/eligibility) */
export interface EligibilityDto {
  product_code: string
  organization_id: string
  eligible: boolean
  reasons: EligibilityReasonDto[]
}

/** Действие с компанией внутри неё: подать заявку, подписать и т. п. */
export type OrgPermission = 'view' | 'submit_application' | 'sign' | 'manage_members' | 'edit_financials'

export interface OrganizationSummaryDto {
  id: string
  name: string
  inn: string
  legal_form: LegalForm
  registry_status: string
  my_role: 'owner' | 'director' | 'accountant' | 'employee' | null
  my_permissions: OrgPermission[]
}

export type ApplicationStatusCode =
  | 'draft'
  | 'submitted'
  | 'in_review'
  | 'info_requested'
  | 'offer_ready'
  | 'signing'
  | 'signed'
  | 'disbursed'
  | 'rejected'
  | 'offer_declined'
  | 'expired'
  | 'cancelled'

export interface LoanRequestDto {
  amount: string | null
  term_months: number | null
  purpose: string | null
  purpose_comment: string | null
}

export interface CollateralInput {
  type: CollateralType
  description: string
  declared_value: number
  owner: 'self' | 'third_party'
}

export interface CollateralDto extends Omit<CollateralInput, 'declared_value'> {
  declared_value: string
}

export interface ConsentsDto {
  personal_data_at: string | null
  credit_bureau_at: string | null
}

export interface DocumentDto {
  id: string
  type: string
  filename: string
  content_type: string
  size_bytes: number
  /** pending_upload | uploaded */
  status: string
  uploaded_at: string | null
  info_request_id: string | null
}

export interface ProductTermsDto {
  code: string
  version: number
  amount_min: string
  amount_max: string
  term_min_months: number
  term_max_months: number
  rate_base: string
  rate_max: string
  repayment_options: string[]
  collateral_required: boolean
  collateral_required_from: string | null
  required_documents: RequiredDocumentDto[]
  application_fields_schema: FieldsSchema
}

/** ApplicationOut — только поля, которые нужны клиентской форме */
export interface ApplicationDto {
  id: string
  number: string
  organization_id: string
  product_code: string
  status: ApplicationStatusCode
  /** Человеческое название этапа процесса, например «Оцениваем заявку» */
  client_stage: string | null
  version: number
  request: LoanRequestDto
  product_fields: Record<string, unknown>
  collateral: CollateralDto | null
  consents: ConsentsDto
  product_terms: ProductTermsDto
  documents: DocumentDto[]
  /** Выдача через АБС после подписи; simulated — мок, реальных денег нет */
  disbursement?: { reference: string; disbursed_at: string; simulated: boolean } | null
  available_actions: string[]
  my_permissions: string[]
  created_at: string
  updated_at: string
  submitted_at: string | null
}

/** Заявка в списке (GET /applications): по всем компаниям клиента, свежие первыми */
export interface ApplicationSummaryDto {
  id: string
  number: string
  organization_id: string
  product_code: string
  status: ApplicationStatusCode
  client_stage: string | null
  /** null — в черновике ещё не указана */
  amount: string | null
  term_months: number | null
  updated_at: string
  submitted_at: string | null
}

export interface ApplicationUpdateInput {
  /** Оптимистичная блокировка: устаревшая версия — 409 version_conflict */
  version: number
  request?: { amount?: number; term_months?: number; purpose?: string; purpose_comment?: string | null }
  /** Сливается с сохранённым, null удаляет ключ */
  product_fields?: Record<string, unknown>
  collateral?: CollateralInput | null
  consents?: { personal_data: boolean; credit_bureau: boolean }
}

export interface CompletenessDto {
  complete: boolean
  violations: { code: string; field: string }[]
}

export interface DocumentUploadInput {
  type: string
  filename: string
  content_type: string
  size_bytes: number
}

export interface PresignedUploadDto {
  url: string
  method: string
  headers: Record<string, string>
  expires_at: string
}

export interface DocumentUploadDto {
  document: DocumentDto
  upload: PresignedUploadDto
}

/* ---------- Кабинет клиента: BFF, лента, новости, компания (docs/api/client-journey.md §3.3–3.7) ---------- */

/** Статус заявки для клиента — его считает BFF (`client_status`) */
export type ClientStatus =
  | 'draft'
  | 'submitted'
  | 'checking'
  | 'scoring'
  | 'info_requested'
  | 'approved'
  | 'counter_offer'
  | 'rejected'
  | 'signing'
  | 'issued'
  | 'cancelled'
  | 'declined'
  | 'expired'

/** Строка списка заявок BFF */
export interface ApplicationRowDto {
  id: string
  number: string
  product_code: string
  product_name: string
  amount: string | null
  term_months: number | null
  status: ApplicationStatusCode
  client_status: ClientStatus
  client_stage: string | null
  /** none | info_requested | offer_ready | signing … — что ждёт от клиента банк */
  action_required: string
  offer_amount: string | null
  offer_rate: string | null
  submitted_at: string | null
  updated_at: string
}

export interface ApplicationListDto {
  items: ApplicationRowDto[]
  total: number
}

/** Запись ленты: событие по заявке или компании */
export interface FeedItemDto {
  id: string
  /** Позиция в потоке и id SSE-события; в ленте дашборда её нет */
  seq?: number
  type: string
  title: string
  body: string
  link: string | null
  /** low | normal | high */
  priority: string
  action_required: boolean
  organization_id: string | null
  application_id: string | null
  created_at: string
  read_at: string | null
}

export interface FeedPageDto {
  items: FeedItemDto[]
  total: number
  limit: number
  offset: number
}

/** Персональная новость: подобрана под ОКВЭД и форму бизнеса компании */
export interface NewsDto {
  id: string
  title: string
  body: string
  published_at: string
  /** Почему новость показана: «ОКВЭД 56.10», «ООО»… */
  relevance: string[]
  read?: boolean
}

/** Предварительно одобренное предложение по продукту */
export interface PreApprovedOfferDto {
  product_code: string
  product_name?: string | null
  max_amount: string
  rate_from: string
  term_max_months: number
  valid_until: string
  /** estimate — по заявленным данным, full — с проверками */
  basis?: 'estimate' | 'full'
  note?: string
}

export interface DashboardDto {
  /** true — у пользователя нет ни одной компании */
  onboarding: boolean
  organization: {
    id: string
    name: string
    inn: string
    legal_form: string
    my_role: string
    my_permissions: OrgPermission[]
    verification_status: string
    registry_status: string
  } | null
  organizations: { id: string; name: string; inn: string; legal_form: string; my_role: string; my_permissions: OrgPermission[] }[]
  counters: {
    active_applications: number
    action_required_count: number
    pre_approved_max_amount: string | null
    pre_approved_rate_from: string | null
    last_activity_at: string | null
  } | null
  pre_approved: PreApprovedOfferDto[]
  active_applications: ApplicationRowDto[]
  todo: { application_id: string; number: string; kind: 'info_requested' | 'offer_ready' | 'signing' | 'consent_required'; title: string }[]
  feed: { unread: number; items: FeedItemDto[] }
  news: NewsDto[]
  /** Какие блоки не загрузились — показываем заглушку, а не ошибку */
  degraded: string[]
}

export interface OfferDto {
  /** as_requested — как просили, counter — контрпредложение */
  kind: 'as_requested' | 'counter' | string
  amount: string
  term_months: number
  rate: string
  monthly_payment: string
  schedule_type: string
  conditions: string[]
  expires_at: string
}

export interface ClientDecisionDto {
  /** APPROVE | COUNTER_OFFER | REJECT | REQUEST_INFO | MANUAL_REVIEW */
  outcome: string
  alternative_product_code: string | null
  client_explanation: string
  improvement_hints: string[]
}

export interface InfoRequestDto {
  id: string
  requested_fields: string[]
  requested_documents: string[]
  comment: string
  created_at: string
  due_at: string | null
  /** open | answered | expired */
  status: string
  answered_at: string | null
}

export interface CardDocumentDto extends DocumentDto {
  review_comment: string | null
}

/** Карточка заявки для клиента (GET /bff/applications/{id}) */
export interface ClientApplicationCardDto {
  id: string
  number: string
  organization: { id: string; name: string; inn: string } | null
  product: {
    code: string
    name: string | null
    amount_min: string
    amount_max: string
    term_min_months: number
    term_max_months: number
    rate_base: string
    rate_max: string
  }
  status: ApplicationStatusCode
  client_status: ClientStatus
  client_stage: string | null
  request: LoanRequestDto | null
  product_fields: Record<string, unknown>
  collateral: CollateralDto | null
  documents: CardDocumentDto[]
  info_request: InfoRequestDto | null
  offer: OfferDto | null
  decision: ClientDecisionDto | null
  timeline: { at: string; kind: string; title: string }[]
  feed: FeedItemDto[]
  /** Что можно сделать сейчас с учётом прав: edit, submit, cancel, accept_offer, decline_offer, sign, answer_info_request, upload_document */
  available_actions: string[]
  my_permissions: string[]
  created_at: string
  updated_at: string
  submitted_at: string | null
  closed_at: string | null
  degraded: string[]
}

export interface SignResultDto {
  application: ApplicationDto
  signature: { signed_at: string; offer_hash: string; edo_document_id: string; simulated: boolean }
}

export interface ContractPaymentDto {
  number: number
  due_date: string | null
  principal: string
  interest: string
  total: string
  balance_after: string
}

/**
 * Договор перед подписью (GET /applications/{id}/contract), с этапа signing и дальше.
 * PDF нет — договор рендерим из полей; offer_hash уходит обратно в подпись.
 */
export interface ContractDto {
  /** Номер заявки: отдельной нумерации договоров нет */
  number: string
  offer_hash: string
  status: 'unsigned' | 'signed'
  borrower: { name: string; inn: string; ogrn: string; kpp: string | null; legal_form: string; head_name: string | null }
  /** Кто вправе подписать сейчас: руководитель по реестру или участник с доверенностью на подпись */
  signers: { account_id: string; name: string; authority: 'registry' | 'power_of_attorney' }[]
  terms: OfferDto
  schedule: {
    amount: string
    term_months: number
    rate: string
    repayment: string
    monthly_payment: string
    total_interest: string
    total_paid: string
    payments: ContractPaymentDto[]
  }
  signature: { signed_by: string; signed_at: string; edo_document_id: string | null; simulated: boolean } | null
}

/** Подбор по потребности (POST /products/recommend), без входа */
export interface NeedInput {
  purpose: LoanPurpose
  amount: number
  term_months: number
}

export interface PublicRecommendationDto {
  rank: number
  /** available | needs_adjustment | unavailable */
  status: 'available' | 'needs_adjustment' | 'unavailable'
  eligible: boolean | null
  fits: boolean
  reasons: EligibilityReasonDto[]
  /** Что поменять, чтобы продукт подошёл */
  adjustments: string[]
  repayment: Repayment
  amount: string
  term_months: number
  monthly_payment_from: string
  monthly_payment_to: string
  product: ProductDto
}

export interface PublicRecommendationsDto {
  purpose: LoanPurpose
  amount: string
  term_months: number
  organization_id?: string | null
  /** Ожидается кассовый разрыв — по выпискам компании */
  cash_gap_expected?: boolean | null
  items: PublicRecommendationDto[]
}

/** Подбор для вошедшего (GET /bff/products/recommend): с проверкой компании и предодобрением */
export interface RecommendationDto {
  product_code: string
  product_name: string
  short_description: string
  rank: number
  fit: string
  eligible: boolean | null
  eligibility: EligibilityReasonDto[]
  rate_from: string
  amount_max: string
  term_max_months: number
  payment_from: string | null
  pre_approved_max: string | null
}

export interface RecommendationsDto {
  items: RecommendationDto[]
  degraded: string[]
}

export interface StreamTicketDto {
  ticket: string
  expires_at: string
  expires_in: number
  stream_url: string
}

/** Карточка компании (GET /organizations/{id}) */
export interface OrganizationDetailDto {
  id: string
  name: string
  inn: string
  legal_form: LegalForm
  registry_status: string
  my_role: OrganizationSummaryDto['my_role']
  my_permissions: OrgPermission[]
  ogrn: string
  kpp: string | null
  registered_at: string
  business_age_months: number
  address: { full: string; region_code: string }
  okved_main: string
  okved_extra: string[]
  tax_regime: string
  employees_count: number
  head_name: string | null
  verification: {
    status: 'unverified' | 'verified' | 'mismatch'
    checked_at: string | null
    discrepancies: { field: string; declared: string | null; registry: string | null }[]
  }
  version: number
}

export interface FinancialReportDto {
  id: string
  period_year: number
  period_quarter: number | null
  source: 'declared' | 'fns' | 'bank_statement'
  revenue: string
  expenses: string | null
  net_profit: string | null
  total_liabilities: string | null
  monthly_debt_payments: string | null
  submitted_by: string | null
  submitted_at: string
}

export interface FinancialReportInput {
  period_year: number
  period_quarter?: number | null
  revenue: number
  expenses?: number | null
  net_profit?: number | null
  total_liabilities?: number | null
  monthly_debt_payments?: number | null
}

export type MemberRole = 'owner' | 'director' | 'accountant' | 'employee'

export interface MemberDto {
  account_id: string
  role: MemberRole
  /** registry — полномочие по ЕГРЮЛ, power_of_attorney — по доверенности */
  authority: 'registry' | 'power_of_attorney' | 'unconfirmed'
  power_of_attorney: { number: string; issued_at: string; valid_until: string; scope: string[]; is_valid: boolean } | null
  permissions: string[]
  added_at: string
  last_name?: string | null
  first_name?: string | null
  middle_name?: string | null
  position?: string | null
}

export interface PowerOfAttorneyInput {
  number: string
  issued_at: string
  valid_until: string
  scope: ('submit_application' | 'sign')[]
}

export interface ProfileInput {
  last_name?: string | null
  first_name?: string | null
  middle_name?: string | null
  position?: string | null
}

export interface ClientApi {
  /** Вход клиента по email или телефону и паролю */
  login(login: string, password: string): Promise<TokenResponse>
  /** Демо-учётки; 404, если на стенде DEMO_LOGIN_ENABLED=false */
  demoAccounts(): Promise<DemoAccountDto[]>
  /** Вход в демо-учётку без пароля */
  demoLogin(login: string): Promise<TokenResponse>
  /** Кто вошёл на сайт — по клиентскому токену */
  me(): Promise<MeDto>
  /** Активные продукты в порядке каталога, без входа */
  listProducts(): Promise<ProductDto[]>
  /** График платежей по базовой ставке продукта, без входа. За рамками продукта — 422 */
  calculate(code: string, input: CalculateInput): Promise<PaymentScheduleDto>
  /** Подходит ли компания под продукт — те же проверки, что при создании заявки */
  eligibility(code: string, organizationId: string): Promise<EligibilityDto>
  /** Компании, где пользователь участник */
  listOrganizations(): Promise<OrganizationSummaryDto[]>
  /** Заявки клиента по всем его компаниям, свежие первыми; limit — до 100 */
  listApplications(limit?: number): Promise<ApplicationSummaryDto[]>
  /** Уже есть заявка по продукту в работе — 409, details.code = duplicate_active, details.application_id */
  createApplication(organizationId: string, productCode: string): Promise<ApplicationDto>
  getApplication(id: string): Promise<ApplicationDto>
  updateApplication(id: string, input: ApplicationUpdateInput): Promise<ApplicationDto>
  completeness(id: string): Promise<CompletenessDto>
  requestDocumentUpload(id: string, input: DocumentUploadInput): Promise<DocumentUploadDto>
  /** Загрузка файла по ссылке из requestDocumentUpload — браузер идёт в хранилище напрямую */
  uploadFile(upload: PresignedUploadDto, file: File): Promise<void>
  confirmDocument(id: string, documentId: string): Promise<DocumentDto>
  deleteDocument(id: string, documentId: string): Promise<void>
  /** Неполная заявка — 422 с details.violations */
  submitApplication(id: string): Promise<ApplicationDto>
  /** Отмена в draft, submitted, info_requested, offer_ready */
  cancelApplication(id: string, reason?: string): Promise<ApplicationDto>

  /** Главная кабинета: компания, предодобрение, заявки, «нужно действие», лента, новости */
  dashboard(organizationId?: string): Promise<DashboardDto>
  /** Заявки компании с клиентским статусом */
  listApplicationRows(organizationId: string, limit?: number): Promise<ApplicationListDto>
  getApplicationCard(id: string): Promise<ClientApplicationCardDto>
  acceptOffer(id: string): Promise<ApplicationDto>
  declineOffer(id: string, reason?: string): Promise<ApplicationDto>
  /** Договор для экрана подписи; до этапа signing — 409 contract_not_ready */
  contract(id: string): Promise<ContractDto>
  /**
   * Подпись: пароль аккаунта ещё раз (step-up), неверный — 422 invalid_password.
   * offerHash — из договора: если предложение изменилось после открытия договора — 409 offer_changed
   */
  sign(id: string, password: string, offerHash: string): Promise<SignResultDto>
  answerInfoRequest(id: string, infoRequestId: string): Promise<ApplicationDto>
  downloadDocument(id: string, documentId: string): Promise<{ url: string }>

  /** Подбор по потребности без входа */
  recommend(need: NeedInput): Promise<PublicRecommendationsDto>
  /** Подбор для вошедшего: проверка компании и предодобренный максимум */
  recommendFor(need: NeedInput, organizationId?: string): Promise<RecommendationsDto>

  feed(query?: { organizationId?: string; applicationId?: string; unreadOnly?: boolean; limit?: number; offset?: number }): Promise<FeedPageDto>
  unreadCount(): Promise<{ count: number }>
  readFeedItem(itemId: string): Promise<FeedItemDto>
  readAllFeed(): Promise<{ updated: number }>
  /** Одноразовый билет для EventSource: он не умеет слать Authorization */
  streamTicket(): Promise<StreamTicketDto>
  news(organizationId?: string, limit?: number): Promise<NewsDto[]>
  readNews(newsId: string): Promise<void>

  getOrganization(id: string): Promise<OrganizationDetailDto>
  financialReports(organizationId: string): Promise<FinancialReportDto[]>
  /** 201 — новый отчёт, 200 — уточнён; запускает пересчёт предодобрения */
  submitFinancialReport(organizationId: string, input: FinancialReportInput): Promise<FinancialReportDto>
  preApprovedOffers(organizationId: string): Promise<PreApprovedOfferDto[]>
  members(organizationId: string): Promise<MemberDto[]>
  addMember(organizationId: string, login: string, role: MemberRole): Promise<MemberDto>
  grantPowerOfAttorney(organizationId: string, accountId: string, input: PowerOfAttorneyInput): Promise<MemberDto>
  updateProfile(input: ProfileInput): Promise<MeDto>
}
