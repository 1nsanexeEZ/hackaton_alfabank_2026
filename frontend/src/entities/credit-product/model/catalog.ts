import type { CreditProduct, ProductCatalog } from './types'

const financials = (requiredFrom: number | null = null) =>
  [
    { type: 'financial_report', title: 'Бухгалтерская отчётность за последний год', requiredFrom, legalForms: ['LLC', 'JSC'] },
    { type: 'tax_return', title: 'Налоговая декларация за последний год', requiredFrom, legalForms: ['IE'] },
  ] as const

/**
 * Демо-каталог для мока админки (заявки, решения, настройки продуктов).
 * Лендинг берёт каталог из API — useProductCatalog. Условия совпадают с backend/seed/products.py.
 */
export const DEMO_CREDIT_PRODUCTS: ProductCatalog = [
  {
    id: 'unsecured',
    code: 'UNSECURED',
    kind: 'lump-sum',
    title: 'Кредит без залога',
    description: 'На пополнение оборотных средств, развитие бизнеса или рефинансирование текущих долгов.',
    rateFrom: 23.5,
    amount: { min: 300_000, max: 30_000_000 },
    termMonths: { min: 12, max: 60 },
    collateral: 'none',
    collateralRequiredFrom: null,
    collateralTypes: [],
    purposes: ['working_capital', 'expansion', 'refinancing', 'contract_execution'],
    repayment: ['annuity', 'differentiated'],
    legalForms: ['LLC', 'IE', 'JSC'],
    requiredDocuments: financials(5_000_000),
    fieldsSchema: {},
    decisionTime: '5 минут',
    keywords: ['Без залога', 'Быстро', 'На любые цели'],
    tag: 'Популярный',
  },
  {
    id: 'secured',
    code: 'SECURED',
    kind: 'lump-sum',
    title: 'Кредит под залог',
    description: 'Крупная сумма на длинный срок под залог недвижимости, транспорта или оборудования.',
    rateFrom: 21.5,
    amount: { min: 500_000, max: 150_000_000 },
    termMonths: { min: 12, max: 120 },
    collateral: 'required',
    collateralRequiredFrom: null,
    collateralTypes: ['real_estate', 'vehicle', 'equipment'],
    purposes: ['working_capital', 'equipment', 'expansion', 'refinancing'],
    repayment: ['annuity', 'differentiated'],
    legalForms: ['LLC', 'IE', 'JSC'],
    requiredDocuments: [
      ...financials(),
      { type: 'collateral_documents', title: 'Документы на залог: право собственности и оценка', requiredFrom: null, legalForms: [] },
    ],
    fieldsSchema: {},
    decisionTime: '1 рабочий день',
    keywords: ['Крупная сумма', 'Надолго', 'Ставка ниже'],
  },
  {
    id: 'credit-line',
    code: 'CREDIT_LINE',
    kind: 'revolving',
    title: 'Кредитная линия',
    description: 'Берите деньги частями в пределах лимита, проценты начисляются только на использованную сумму.',
    rateFrom: 22,
    amount: { min: 1_000_000, max: 50_000_000 },
    termMonths: { min: 12, max: 36 },
    collateral: 'optional',
    collateralRequiredFrom: 30_000_000,
    collateralTypes: ['real_estate', 'vehicle', 'equipment', 'goods'],
    purposes: ['working_capital', 'cash_gap', 'contract_execution'],
    repayment: ['interest_only', 'annuity'],
    legalForms: ['LLC', 'IE', 'JSC'],
    requiredDocuments: financials(),
    fieldsSchema: {},
    decisionTime: '1 рабочий день',
    keywords: ['Частями', 'Свой лимит', 'Гибко'],
  },
  {
    id: 'overdraft',
    code: 'OVERDRAFT',
    kind: 'revolving',
    title: 'Овердрафт',
    description: 'Платите поставщикам и налоги, даже когда на расчётном счёте временно не хватает денег.',
    rateFrom: 24,
    amount: { min: 100_000, max: 10_000_000 },
    termMonths: { min: 3, max: 12 },
    collateral: 'none',
    collateralRequiredFrom: null,
    collateralTypes: [],
    purposes: ['cash_gap'],
    repayment: ['interest_only'],
    legalForms: ['LLC', 'IE', 'JSC'],
    requiredDocuments: [
      { type: 'bank_statement', title: 'Выписка по расчётному счёту за 6 месяцев (CSV)', requiredFrom: null, legalForms: [] },
    ],
    fieldsSchema: {},
    decisionTime: '5 минут',
    keywords: ['Кассовый разрыв', 'Сразу', 'Подушка'],
  },
]

export function findProduct(catalog: ProductCatalog, id: string): CreditProduct {
  return catalog.find((product) => product.id === id) ?? catalog[0]
}
