import type { FieldsSchema, LoanPurpose, Repayment } from '@/shared/api'

/** Как клиент получает деньги: всей суммой сразу или частями в пределах лимита */
export type ProductKind = 'lump-sum' | 'revolving'

export type Collateral = 'none' | 'required' | 'optional'

export interface NumberRange {
  min: number
  max: number
}

export interface RequiredDocument {
  type: string
  title: string
  /** Нужен только начиная с этой суммы; null — всегда */
  requiredFrom: number | null
  /** Для каких форм бизнеса (LLC, IE, JSC); пусто — для всех */
  legalForms: readonly string[]
}

export interface CreditProduct {
  /** Идентификатор для витрины (frontend_id бэкенда): unsecured, credit-line… */
  id: string
  /** Код продукта в API: UNSECURED, CREDIT_LINE… */
  code: string
  kind: ProductKind
  title: string
  description: string
  /** Базовая годовая ставка, % */
  rateFrom: number
  /** Сумма, ₽ */
  amount: NumberRange
  termMonths: NumberRange
  collateral: Collateral
  /** С какой суммы залог обязателен, даже если в целом он по желанию */
  collateralRequiredFrom: number | null
  /** Что можно дать в залог: real_estate, vehicle… */
  collateralTypes: readonly string[]
  purposes: readonly LoanPurpose[]
  /** Схемы погашения; первая — по умолчанию */
  repayment: readonly Repayment[]
  /** Формы бизнеса, которым продукт доступен */
  legalForms: readonly string[]
  requiredDocuments: readonly RequiredDocument[]
  /** Дополнительные поля заявки продукта (JSON Schema) */
  fieldsSchema: FieldsSchema
  /** Типичное время решения, например «5 минут» */
  decisionTime: string
  /** 2–3 слова, которые продают продукт с первого взгляда — для компактной витрины */
  keywords: readonly string[]
  tag?: string
}

/** Каталог никогда не пустой: калькулятору и форме всегда есть что выбрать по умолчанию */
export type ProductCatalog = readonly [CreditProduct, ...CreditProduct[]]

export const PRODUCT_KIND_LABEL: Record<ProductKind, string> = {
  'lump-sum': 'Одной суммой',
  revolving: 'Деньги частями',
}

export const COLLATERAL_LABEL: Record<Collateral, string> = {
  none: 'Без залога',
  required: 'С залогом',
  optional: 'Залог по желанию',
}

export const PURPOSE_LABEL: Record<LoanPurpose, string> = {
  working_capital: 'Пополнение оборотных средств',
  cash_gap: 'Закрыть кассовый разрыв',
  equipment: 'Покупка оборудования',
  vehicles: 'Покупка транспорта',
  real_estate: 'Покупка недвижимости',
  contract_execution: 'Исполнение контракта',
  refinancing: 'Рефинансирование кредитов',
  expansion: 'Развитие бизнеса',
}

export const COLLATERAL_TYPE_LABEL: Record<string, string> = {
  real_estate: 'Недвижимость',
  equipment: 'Оборудование',
  vehicle: 'Транспорт',
  goods: 'Товары в обороте',
}

export const REPAYMENT_LABEL: Record<Repayment, string> = {
  annuity: 'Равными платежами',
  differentiated: 'Платёж уменьшается',
  interest_only: 'Проценты каждый месяц, долг в конце',
  by_contract_schedule: 'По графику контракта',
}
