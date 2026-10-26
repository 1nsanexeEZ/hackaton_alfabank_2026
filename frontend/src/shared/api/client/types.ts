import type { DownloadedFile, Page } from '../http'
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
  /** Деньги идут на заявленную цель: транспорт, недвижимость, другие кредиты */
  target_use_confirmation: boolean
  /** Программа господдержки: клиенту — не выше её ставки */
  support_program: SupportProgramDto | null
  min_business_age_months: number
  allowed_legal_forms: string[]
  min_annual_revenue: string | null
  required_documents: RequiredDocumentDto[]
  application_fields_schema: FieldsSchema
  /** BPMN-маршрут заявки (GET /workflows) */
  workflow_code: string
  auto_decision_limit: string
  status: ProductStatus
  /** Только для стартапа (бизнес младше 6 месяцев или без годового отчёта) */
  startup_only?: boolean
  /** Витрина: короткие слова для карточки (до 5), метка вроде «Популярный» и привычное время решения */
  keywords: string[]
  tag: string | null
  decision_time: string | null
}

/** draft — ещё не в каталоге, active — в продаже, archived — снят с продажи или заменён новой версией */
export type ProductStatus = 'draft' | 'active' | 'archived'

export interface SupportProgramDto {
  code: string
  name: string
  rate_cap: string
  msp_registry_required: boolean
  /** Двузначные классы ОКВЭД; пусто — любая отрасль */
  okved_whitelist: string[]
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

/** Третье лицо в сделке: физлицо — ФИО, организация или ИП — наименование и ИНН */
export interface ThirdPartyInput {
  kind: 'person' | 'organization'
  name: string
  /** Обязателен у организации, у физлица — по желанию */
  inn?: string | null
  /** Страна, если не Россия: ISO 3166-1 alpha-2 */
  country?: string | null
}

export interface ThirdPartyDto {
  kind: 'person' | 'organization'
  name: string
  inn: string | null
  country?: string | null
}

export interface CollateralInput {
  type: CollateralType
  description: string
  declared_value: number
  owner: 'self' | 'third_party'
  /** Владелец залога — только при owner = third_party, при self бэкенд вернёт ошибку */
  owner_party?: ThirdPartyInput | null
}

export interface CollateralDto extends Omit<CollateralInput, 'declared_value' | 'owner_party'> {
  declared_value: string
  owner_party?: ThirdPartyDto | null
}

/** Основание действовать в интересах третьего лица: агентский договор, поручение, комиссия, доверительное управление */
export type BeneficiaryBasis = 'agency' | 'mandate' | 'commission' | 'trust_management'

/** Ответ клиента: действует ли он в интересах третьего лица (выгодоприобретателя); «нет» — тоже ответ */
export interface BeneficiaryInput {
  acts_for_third_party: boolean
  /** При true обязательны beneficiary и basis */
  beneficiary?: ThirdPartyInput | null
  basis?: BeneficiaryBasis | null
}

export interface BeneficiaryDto {
  acts_for_third_party: boolean
  beneficiary: ThirdPartyDto | null
  basis: BeneficiaryBasis | null
  declared_by?: string
  declared_at: string
}

/**
 * Бенефициар со слов клиента (115-ФЗ ст. 6.1): ownership — владеет больше 25% прямо или через другие компании,
 * control — иначе контролирует действия компании, например по договору
 */
export interface BeneficialOwnerInput {
  name: string
  basis: 'ownership' | 'control'
  /** Страна, если не Россия: ISO 3166-1 alpha-2 */
  country?: string | null
}

/** Ответ о бенефициарах; пустой список — тоже ответ: больше 25% ни у кого и никто не контролирует компанию иначе */
export interface BeneficialOwnersDto {
  owners: (BeneficialOwnerInput & { country: string | null })[]
  declared_by?: string
  declared_at: string
}

/** Откуда согласие в заявке: application — галочка в черновике, profile — взято из профиля */
export type ConsentSource = 'application' | 'profile'

export interface ConsentsDto {
  personal_data_at: string | null
  credit_bureau_at: string | null
  /** Согласие на решение только автоматикой (ст. 16 152-ФЗ) — важно только у ИП */
  automated_decision_at?: string | null
  personal_data_source?: ConsentSource | null
  credit_bureau_source?: ConsentSource | null
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
  /** Ответ о третьем лице; null — клиент ещё не ответил */
  beneficiary?: BeneficiaryDto | null
  /** Ответ о бенефициарах; null — клиент ещё не ответил, подачу это не блокирует */
  beneficial_owners?: BeneficialOwnersDto | null
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
  /** null — отозвать ответ; не передано — ответ не меняется */
  beneficiary?: BeneficiaryInput | null
  /** Бенефициары со слов клиента; null — снять ответ, не передано — не меняется */
  beneficial_owners?: { owners: BeneficialOwnerInput[] } | null
  consents?: { personal_data: boolean; credit_bureau: boolean; automated_decision?: boolean }
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

/** Часть ленты: записи одной компании или одной заявки */
export interface FeedScope {
  organizationId?: string
  applicationId?: string
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
  basis?: PreApprovalBasis
  note?: string
}

/** estimate — по заявленным данным, full — с проверками, project — по проектной оценке стартапа */
export type PreApprovalBasis = 'estimate' | 'full' | 'project'

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
    /** startup — бизнес младше 6 месяцев или без годового отчёта: ему — только продукты для стартапа */
    segment?: CompanySegment
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
  /** Только у стартапа: предскрининг учредителя, ревизия бизнес-плана и проектная оценка; null — шага ещё не было */
  startup?: {
    prescreen: FounderPrescreenSummaryDto | null
    business_plan_revision?: number | null
    project?: ProjectAssessmentDto | null
  } | null
  /** Согласия, которые банк просит до заявки: что дано и чего нет */
  consents?: ConsentStateDto[]
}

/** Согласие до заявки на дашборде: scope account — даёт сам пользователь, organization — представитель компании */
export interface ConsentStateDto {
  type: 'personal_data' | 'credit_bureau_company' | 'credit_bureau_personal'
  scope: 'account' | 'organization'
  title: string
  purpose: string
  /** Без него заявку не подать */
  required: boolean
  /** Действует сейчас: дано, не отозвано, не истекло */
  given: boolean
  given_at: string | null
  valid_until: string | null
}

/** Согласие компании на запрос её кредитной истории; даёт и отзывает любой представитель с правом подавать заявки */
export interface OrganizationConsentDto {
  type: 'credit_bureau_company'
  organization_id: string
  given_at: string
  given_by: string
  valid_until: string | null
  revoked_at: string | null
  revoked_by: string | null
  active: boolean
  text_version: string
}

/** Месяц финмодели стартапа: операционные выручка и расходы, без платежей по кредиту */
export interface PlanMonthDto {
  revenue: string
  expenses: string
}

/** Финмодель по шаблону банка: ровно 24 месяца от начала проекта */
export interface FinancialModelDto {
  months: PlanMonthDto[]
  own_funds: string
  collateral_value: string
  collateral_description: string | null
  /** none — без гарантии, msp_corporation — Корпорация МСП, regional_fund — региональная гарантийная организация */
  guarantee: 'none' | 'msp_corporation' | 'regional_fund'
  /** Доля гарантии, 0–1; без гарантии — 0 */
  guarantee_share: string
  loan_amount: string
  loan_term_months: number
}

export interface BusinessPlanInput {
  summary: string
  financial_model: Omit<FinancialModelDto, 'months'> & { months: { revenue: string | number; expenses: string | number }[] }
}

/** Бизнес-план стартапа в кабинете компании; revision растёт с каждым уточнением */
export interface BusinessPlanDto {
  organization_id: string
  summary: string
  financial_model: FinancialModelDto
  submitted_by: string | null
  submitted_at: string
  revision: number
}

/** Проектная оценка стартапа: passed — «вам предодобрен кредит до max_amount»; действует 30 дней */
export interface ProjectAssessmentDto {
  status: 'passed' | 'failed'
  product_code: string
  max_amount: string | null
  /** По какой ревизии бизнес-плана оценивали: меньше текущей — план поменяли, стоит оценить заново */
  plan_revision: number
  checked_at: string
  valid_until: string
  valid: boolean
  reasons: EligibilityReasonDto[]
}

export type CompanySegment = 'established' | 'startup'

/** Предскрининг учредителя стартапа по его личной кредитной истории; действует 30 дней */
export interface FounderPrescreenDto {
  status: 'passed' | 'failed'
  founder: { account_id: string; name: string }
  checked_at: string
  valid_until: string
  /** Пройден и ещё не истёк */
  valid: boolean
  reasons: EligibilityReasonDto[]
}

/** Тот же предскрининг в дашборде: вместо founder — только имя */
export interface FounderPrescreenSummaryDto extends Omit<FounderPrescreenDto, 'founder'> {
  founder_name: string
}

/** Личные согласия на аккаунте; согласие компании — отдельно, через /organizations/{id}/consents */
export type ConsentType = 'personal_data' | 'credit_bureau_personal'

/** Личное согласие на аккаунте: ПДн бессрочно, БКИ физлица — 6 месяцев */
export interface ConsentDto {
  type: ConsentType
  given_at: string
  valid_until: string | null
  revoked_at: string | null
  /** Не отозвано и не истекло */
  active: boolean
  text_version: string
}

/** Калькулятор с учётом предодобрения компании (POST /bff/products/{code}/calculate) */
export interface PersonalScheduleDto {
  schedule: PaymentScheduleDto
  pre_approved: { max_amount: string; rate_from: string; term_max_months: number; valid_until: string; basis: PreApprovalBasis } | null
  /** null — по этому продукту ничего не предодобрено */
  within_pre_approved: boolean | null
  eligible: boolean
  /** Причины eligibility и amount_above_pre_approved / term_above_pre_approved */
  reasons: EligibilityReasonDto[]
  /** Запрос, урезанный до посильного */
  suggestion: { amount: string; term_months: number; monthly_payment: string } | null
  /** Посильный максимум на выбранный срок; null — предодобрения нет */
  max_affordable?: string | null
  /** Что ограничило максимум: предодобрение, платёжеспособность по отчётности, проектная оценка */
  affordable_by?: 'pre_approved' | 'payment' | 'project' | null
  /** Запрос больше посильного: заявку примут, решит специалист */
  above_affordable?: boolean
  degraded: string[]
}

/** Итог ручной сверки компании с ЕГРЮЛ/ЕГРИП */
export interface VerificationResultDto {
  organization: OrganizationDetailDto
  /** Что обновили молча: наименование, адрес, КПП, ОКВЭД, статус */
  updated_fields: { field: string; before: string | null; after: string | null }[]
  /** Что не меняем сами: руководитель */
  discrepancies: { field: string; declared: string | null; registry: string | null }[]
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
  /** Дал ли руководитель по реестру согласие на запрос своей кредитной истории; null — руководителя нет */
  consents?: { head_credit_bureau: { required: boolean; given: boolean; given_at: string | null; head_name: string } | null }
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
 * PDF договора. draft — проект до подписи, signed — итоговый: с листом подписания и подписью банка.
 * Пока документ формируется (pending), id и sha256 — null; при сбое (failed) бэкенд может прислать только status.
 */
export interface ContractDocumentDto {
  id?: string | null
  kind?: 'draft' | 'signed'
  status: 'pending' | 'ready' | 'failed'
  /** SHA-256 файла; у проекта это document_hash для подписи */
  sha256?: string | null
  created_at?: string | null
  filename?: string | null
  /** Публичная страница проверки — только у подписанного и готового */
  verify_url?: string | null
}

/**
 * Договор перед подписью (GET /applications/{id}/contract), с этапа signing и дальше.
 * Условия рендерим из полей; offer_hash уходит обратно в подпись. Поля uid и document есть
 * только у бэкенда с PDF договора — со старым бэкендом их нет, и подпись идёт как раньше.
 */
export interface ContractDto {
  /** Номер заявки: отдельной нумерации договоров нет */
  number: string
  /** УИд договора (218-ФЗ): UUID и контрольный символ */
  uid?: string
  /** PDF договора: проект и состояние формирования */
  document: ContractDocumentDto
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

/** Правила электронного взаимодействия (GET /esign/rules) — соглашение о простой электронной подписи */
export interface EsignRulesDto {
  version: string
  title: string
  effective_from: string
  /** Обычный текст абзацами, без разметки */
  paragraphs: string[]
}

export interface ContractSignatureDto {
  party: 'client' | 'bank'
  /** simple — простая (пароль от кабинета), advanced — усиленная (ключ банка) */
  type: 'simple' | 'advanced'
  signer: string
  role: string | null
  /** registry — полномочие по ЕГРЮЛ, power_of_attorney — по доверенности */
  authority: 'registry' | 'power_of_attorney' | null
  signed_at: string
  /** password — пароль от кабинета, pades — подпись внутри PDF */
  method: string
  rules_version: string | null
  /** Метка времени к подписи банка */
  timestamp_at: string | null
  certificate: { serial: string; subject: string; issuer: string; valid_from: string; valid_to: string } | null
}

/** Публичная проверка по QR (GET /contracts/verify/{document_id}) */
export interface ContractVerificationDto {
  document_id: string
  number: string
  uid: string
  kind: 'draft' | 'signed'
  sha256: string
  created_at: string
  borrower: string
  signatures: ContractSignatureDto[]
  /** Журнал подписания цел: хеш-цепочка записей не нарушена */
  log_intact: boolean
  /** Ключ банка — демо-стенда, не квалифицированный */
  demo: boolean
}

export type FileVerificationProblem =
  | 'not_in_archive'
  | 'no_signature'
  | 'signature_broken'
  | 'untrusted_certificate'
  | 'draft_not_signed'

/** Проверка загруженного PDF (POST /contracts/verify) */
export interface FileVerificationDto {
  /** Итог: подпись цела, сертификат доверенный, файл совпал с архивом */
  valid: boolean
  /** null — файла нет в архиве */
  document_id: string | null
  matches_archive: boolean
  signature: {
    present: boolean
    /** Файл не менялся после подписи */
    intact: boolean
    trusted: boolean
    signer: string | null
    signed_at: string | null
    timestamp_at: string | null
  }
  problems: (FileVerificationProblem | string)[]
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

/* ---------- Техподдержка: обращения клиента и переписка (модуль support, #210) ---------- */

/** open — ждёт, кто возьмёт; in_progress — ведёт сотрудник; resolved — решено, ответ клиента вернёт в работу; closed — закрыто */
export type SupportTicketStatus = 'open' | 'in_progress' | 'resolved' | 'closed'
export type SupportSide = 'client' | 'staff'

export interface SupportMessageDto {
  id: string
  author_id: string
  author_name: string | null
  side: SupportSide
  text: string
  created_at: string
}

/** Обращение в списке */
export interface SupportTicketListItemDto {
  id: string
  /** ТП-2026-000001 */
  number: string
  subject: string
  status: SupportTicketStatus
  author_id: string
  organization_id: string | null
  application_id: string | null
  /** Сотрудник, который взял обращение */
  assignee_id: string | null
  taken_at: string | null
  resolved_at: string | null
  closed_at: string | null
  message_count: number
  last_message_at: string | null
  /** client в незакрытом обращении — банк должен ответить */
  last_message_side: SupportSide | null
  version: number
  created_at: string
  updated_at: string
}

/** Обращение с перепиской — так отвечают все ручки, кроме списков */
export interface SupportTicketDto extends SupportTicketListItemDto {
  author_name: string | null
  assignee_name: string | null
  messages: SupportMessageDto[]
}

export interface SupportTicketInput {
  /** До 200 символов */
  subject: string
  /** Первое сообщение, до 4000 символов */
  text: string
  /** Компания вопроса — клиент её участник */
  organization_id?: string | null
  /** Заявка вопроса: её компания станет компанией обращения */
  application_id?: string | null
}

/** Откуда ставка: введена в админке, из cbr.ru или — если на дату ничего нет — KEY_RATE из настроек */
export type KeyRateSource = 'admin' | 'cbr' | 'settings'

/** Ключевая ставка Банка России на дату (GET /market/key-rate): от неё считаются ставки каталога */
export interface KeyRateDto {
  /** Процент годовых строкой: «14.00» */
  value: string
  /** С какой даты действует; null — ставки на дату нет, взята из настроек */
  effective_from: string | null
  source: KeyRateSource
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
  /** Ключевая ставка на дату (ГГГГ-ММ-ДД), по умолчанию — на сегодня; без входа */
  keyRate(on?: string): Promise<KeyRateDto>
  /** Активные продукты в порядке каталога, без входа */
  /** Продукты в продаже; purpose — только подходящие под цель кредита */
  listProducts(purpose?: LoanPurpose): Promise<ProductDto[]>
  /** График платежей по базовой ставке продукта, без входа. За рамками продукта — 422 */
  calculate(code: string, input: CalculateInput): Promise<PaymentScheduleDto>
  /** Подходит ли компания под продукт — те же проверки, что при создании заявки */
  eligibility(code: string, organizationId: string): Promise<EligibilityDto>
  /** Компании, где пользователь участник */
  listOrganizations(): Promise<OrganizationSummaryDto[]>
  /** Заявки клиента по всем его компаниям, свежие первыми; limit — до 100 */
  /** Заявки моих компаний; status повторяется в query, limit до 100 */
  listApplications(query?: { organizationId?: string; status?: ApplicationStatusCode[]; limit?: number; offset?: number }): Promise<ApplicationSummaryDto[]>
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
  /** Строки BFF по компании: черновиков нет; status — статус бэкенда, limit до 100, total — сколько всего */
  listApplicationRows(organizationId: string, query?: { status?: string; limit?: number; offset?: number }): Promise<ApplicationListDto>
  getApplicationCard(id: string): Promise<ClientApplicationCardDto>
  acceptOffer(id: string): Promise<ApplicationDto>
  declineOffer(id: string, reason?: string): Promise<ApplicationDto>
  /** Договор для экрана подписи; до этапа signing — 409 contract_not_ready */
  contract(id: string): Promise<ContractDto>
  /**
   * Подпись: пароль аккаунта ещё раз (step-up), неверный — 422 invalid_password.
   * offerHash — из договора: если предложение изменилось после открытия договора — 409 offer_changed.
   * documentHash — SHA-256 проекта PDF, который видел клиент (пересобран — 422 document_changed, ещё не готов —
   * 409 document_pending); rulesVersion — принятая редакция Правил ЭП (устарела — 422 rules_outdated).
   * Со старым бэкендом оба не передаём
   */
  sign(id: string, password: string, offerHash: string, documentHash?: string, rulesVersion?: string): Promise<SignResultDto>
  /** PDF договора; kind не задан — последний готовый. Не готов — 409 document_pending */
  downloadContractDocument(id: string, kind?: 'draft' | 'signed'): Promise<DownloadedFile>
  /** Правила электронного взаимодействия — без входа */
  esignRules(): Promise<EsignRulesDto>
  /** Публичная проверка договора по QR; нет в архиве — 404 document_not_found */
  verifyContract(documentId: string): Promise<ContractVerificationDto>
  /** Проверка загруженного PDF; не PDF — 422 not_a_pdf, больше 10 МБ — 413 file_too_large */
  verifyContractFile(file: File): Promise<FileVerificationDto>
  answerInfoRequest(id: string, infoRequestId: string): Promise<ApplicationDto>
  downloadDocument(id: string, documentId: string): Promise<{ url: string }>

  /** Подбор по потребности без входа */
  recommend(need: NeedInput): Promise<PublicRecommendationsDto>
  /** Подбор для вошедшего: проверка компании и предодобренный максимум */
  recommendFor(need: NeedInput, organizationId?: string): Promise<RecommendationsDto>

  feed(query?: { organizationId?: string; applicationId?: string; unreadOnly?: boolean; limit?: number; offset?: number }): Promise<FeedPageDto>
  /** Без фильтра — по всей ленте; с компанией или заявкой — только по ним */
  unreadCount(scope?: FeedScope): Promise<{ count: number }>
  readFeedItem(itemId: string): Promise<FeedItemDto>
  readAllFeed(scope?: FeedScope): Promise<{ updated: number }>
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
  /** Номер — по формату, уникален в компании (422 invalid_format, 409 number_taken); одна на участника — 409 power_of_attorney_exists */
  grantPowerOfAttorney(organizationId: string, accountId: string, input: PowerOfAttorneyInput): Promise<MemberDto>
  /** Отозвать доверенность: отзывает тот, кто выдаёт; нет доверенности — 404 power_of_attorney_not_found */
  revokePowerOfAttorney(organizationId: string, accountId: string): Promise<MemberDto>
  changeMemberRole(organizationId: string, accountId: string, role: MemberRole): Promise<MemberDto>
  removeMember(organizationId: string, accountId: string): Promise<void>
  /** Сверить с ЕГРЮЛ/ЕГРИП мимо кэша и подкачать изменения */
  verifyOrganization(organizationId: string): Promise<VerificationResultDto>
  updateProfile(input: ProfileInput): Promise<MeDto>

  /** Личные согласия: действующие и история, новые сверху */
  consents(): Promise<ConsentDto[]>
  giveConsents(types: ConsentType[]): Promise<ConsentDto[]>
  /** Отзыв; повторный отзыв — тоже 204 */
  revokeConsent(type: ConsentType): Promise<void>

  /** Калькулятор по ставке предодобрения компании; ставку задаёт бэкенд */
  calculateFor(code: string, organizationId: string, input: Omit<CalculateInput, 'rate'>): Promise<PersonalScheduleDto>

  /** Предскрининг учредителя: 422 consent_required — нет согласия на БКИ физлица, founder_not_found — учредителя нет среди участников */
  runFounderPrescreen(organizationId: string): Promise<FounderPrescreenDto>
  /** Последний предскрининг; 404 — ещё не было */
  founderPrescreen(organizationId: string): Promise<FounderPrescreenDto>

  /** Согласия компании: действующие и история, новые сверху */
  organizationConsents(organizationId: string): Promise<OrganizationConsentDto[]>
  giveOrganizationConsents(organizationId: string, types: OrganizationConsentDto['type'][]): Promise<OrganizationConsentDto[]>
  /** Отзыв любым представителем с правом подавать заявки; повторный — тоже 204 */
  revokeOrganizationConsent(organizationId: string, type: OrganizationConsentDto['type']): Promise<void>

  /** Бизнес-план стартапа; 404 — ещё не заполнен */
  businessPlan(organizationId: string): Promise<BusinessPlanDto>
  /** 201 — новый, 200 — уточнён (revision +1); право edit_financials */
  submitBusinessPlan(organizationId: string, input: BusinessPlanInput): Promise<BusinessPlanDto>
  /** Последняя проектная оценка; 404 — ещё не было */
  projectAssessment(organizationId: string): Promise<ProjectAssessmentDto>
  /** Оценить проект по текущему плану; 422 business_plan_required, product_not_eligible */
  runProjectAssessment(organizationId: string): Promise<ProjectAssessmentDto>
  /** Мои обращения в поддержку, свежие сверху */
  /** total — сколько обращений всего по тому же фильтру */
  supportTickets(query?: { status?: SupportTicketStatus[]; limit?: number; offset?: number }): Promise<Page<SupportTicketListItemDto>>
  /** Чужое — 404 */
  supportTicket(id: string): Promise<SupportTicketDto>
  openSupportTicket(input: SupportTicketInput): Promise<SupportTicketDto>
  /** В закрытое — 409 ticket_closed; решённое возвращается в работу */
  postSupportMessage(id: string, text: string): Promise<SupportTicketDto>
  closeSupportTicket(id: string): Promise<SupportTicketDto>
}
