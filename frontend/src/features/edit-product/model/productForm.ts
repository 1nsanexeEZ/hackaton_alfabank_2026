import type {
  CollateralKind,
  CollateralType,
  Facility,
  LegalForm,
  LoanPurpose,
  ProductCreateInput,
  ProductDto,
  ProductInput,
  Repayment,
} from '@/shared/api'
import { onlyDigits } from '@/shared/lib'

/**
 * Форма условий продукта. В ней — то, что меняют чаще всего: суммы, сроки, ставки, авторешение,
 * кому продукт подходит, залог и маршрут. Остальное (документы, доп. поля заявки, господдержка,
 * полное описание) берём из продукта как есть: PUT требует карточку целиком.
 */
export type Guarantee = ProductDto['guarantee']

export interface ProductForm {
  code: string
  frontendId: string
  name: string
  shortDescription: string
  amountMin: string
  amountMax: string
  termMin: string
  termMax: string
  rateBase: string
  rateMax: string
  autoDecisionLimit: string
  purposes: LoanPurpose[]
  facility: Facility
  /** Первый — график по умолчанию */
  repayment: Repayment[]
  legalForms: LegalForm[]
  minBusinessAge: string
  minRevenue: string
  startupOnly: boolean
  collateralKind: CollateralKind
  collateralTypes: CollateralType[]
  collateralFrom: string
  guarantee: Guarantee
  targetUse: boolean
  workflowCode: string
}

export type ProductFormErrors = Partial<Record<keyof ProductForm, string>>

const money = (value: string | null) => (value === null ? '' : Number(value).toLocaleString('ru-RU'))
const rate = (value: string) => String(Number(value)).replace('.', ',')

export function toForm(product: ProductDto | null): ProductForm {
  return {
    code: product?.code ?? '',
    frontendId: product?.frontend_id ?? '',
    name: product?.name ?? '',
    shortDescription: product?.short_description ?? '',
    amountMin: product ? money(product.amount_min) : '',
    amountMax: product ? money(product.amount_max) : '',
    termMin: product ? String(product.term_min_months) : '',
    termMax: product ? String(product.term_max_months) : '',
    rateBase: product ? rate(product.rate_base) : '',
    rateMax: product ? rate(product.rate_max) : '',
    autoDecisionLimit: product ? money(product.auto_decision_limit) : '0',
    purposes: [...(product?.purposes ?? ['working_capital'])],
    facility: product?.facility ?? 'term_loan',
    repayment: [...(product?.repayment_options ?? ['annuity'])],
    legalForms: [...((product?.allowed_legal_forms as LegalForm[] | undefined) ?? ['LLC', 'IE', 'JSC'])],
    minBusinessAge: String(product?.min_business_age_months ?? 0),
    minRevenue: money(product?.min_annual_revenue ?? null),
    startupOnly: product?.startup_only ?? false,
    collateralKind: product?.collateral_kind ?? 'none',
    collateralTypes: [...((product?.collateral_types as CollateralType[] | undefined) ?? [])],
    collateralFrom: money(product?.collateral_required_from ?? null),
    guarantee: product?.guarantee ?? 'none',
    targetUse: product?.target_use_confirmation ?? false,
    workflowCode: product?.workflow_code ?? '',
  }
}

const amount = (value: string) => Number(onlyDigits(value))
const percent = (value: string) => Number(value.trim().replace(',', '.'))

export function validate(form: ProductForm, isNew: boolean): ProductFormErrors {
  const errors: ProductFormErrors = {}
  if (isNew) {
    if (!/^[A-Z][A-Z0-9_]{1,31}$/.test(form.code.trim())) errors.code = 'Латиница в верхнем регистре, цифры и _, до 32 знаков'
    if (!/^[a-z][a-z0-9-]{1,31}$/.test(form.frontendId.trim())) errors.frontendId = 'Латиница в нижнем регистре, цифры и -, до 32 знаков'
  }
  if (!form.name.trim()) errors.name = 'Укажите название'
  if (!form.shortDescription.trim()) errors.shortDescription = 'Пара слов о продукте для каталога'
  if (!(amount(form.amountMin) > 0)) errors.amountMin = 'Больше нуля'
  if (!(amount(form.amountMax) >= amount(form.amountMin))) errors.amountMax = 'Не меньше суммы «от»'
  const termMin = Number(onlyDigits(form.termMin))
  const termMax = Number(onlyDigits(form.termMax))
  if (!(termMin >= 1)) errors.termMin = 'От 1 месяца'
  if (!(termMax >= termMin)) errors.termMax = 'Не меньше срока «от»'
  const base = percent(form.rateBase)
  const max = percent(form.rateMax)
  if (!(base >= 0 && base <= 100)) errors.rateBase = 'От 0 до 100%'
  if (!(max >= base && max <= 100)) errors.rateMax = 'Не ниже ставки «от» и до 100%'
  if (!form.purposes.length) errors.purposes = 'Хотя бы одна цель'
  if (!form.repayment.length) errors.repayment = 'Хотя бы один график'
  if (!form.legalForms.length) errors.legalForms = 'Хотя бы одна форма бизнеса'
  if (!form.workflowCode) errors.workflowCode = 'Выберите маршрут'
  return errors
}

/** Карточка для PUT: изменённое из формы, остальное — из продукта, на основе которого правим */
export function toInput(form: ProductForm, base: ProductDto | null): ProductInput {
  // Пусто или ноль — ограничения нет
  const optionalAmount = (value: string) => (amount(value) > 0 ? String(amount(value)) : null)
  return {
    frontend_id: form.frontendId.trim(),
    name: form.name.trim(),
    short_description: form.shortDescription.trim(),
    description_plain: base?.description_plain ?? '',
    purposes: form.purposes,
    facility: form.facility,
    repayment_options: form.repayment,
    amount_min: String(amount(form.amountMin)),
    amount_max: String(amount(form.amountMax)),
    term_min_months: Number(onlyDigits(form.termMin)),
    term_max_months: Number(onlyDigits(form.termMax)),
    rate_base: String(percent(form.rateBase)),
    rate_max: String(percent(form.rateMax)),
    collateral_kind: form.collateralKind,
    collateral_types: form.collateralKind === 'none' ? [] : form.collateralTypes,
    collateral_required_from: form.collateralKind === 'optional' ? optionalAmount(form.collateralFrom) : null,
    guarantee: form.guarantee,
    target_use_confirmation: form.targetUse,
    support_program: base?.support_program ?? null,
    min_business_age_months: Number(onlyDigits(form.minBusinessAge) || 0),
    allowed_legal_forms: form.legalForms,
    min_annual_revenue: optionalAmount(form.minRevenue),
    startup_only: form.startupOnly,
    required_documents: base?.required_documents ?? [],
    application_fields_schema: base?.application_fields_schema ?? {},
    workflow_code: form.workflowCode,
    auto_decision_limit: String(amount(form.autoDecisionLimit)),
  }
}

export function toCreateInput(form: ProductForm, base: ProductDto | null, publish: boolean): ProductCreateInput {
  return { ...toInput(form, base), code: form.code.trim(), status: publish ? 'active' : 'draft' }
}
