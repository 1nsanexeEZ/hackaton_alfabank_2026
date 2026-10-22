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
  available_actions: string[]
  my_permissions: string[]
  created_at: string
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
  /** Компании, где пользователь участник */
  listOrganizations(): Promise<OrganizationSummaryDto[]>
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
  cancelApplication(id: string): Promise<ApplicationDto>
}
