import { describe, expect, it } from 'vitest'

import type { ProductDto } from '@/shared/api'

import { toCreditProduct } from './mapper'
import { amountStep, hasProductFields, isAvailableFor, needsCollateral, requiredDocumentsFor, termStep } from './rules'

/** Продукт каталога как его отдаёт GET /products — по умолчанию «Кредит без залога» */
function productDto(overrides: Partial<ProductDto> = {}): ProductDto {
  return {
    code: 'UNSECURED',
    frontend_id: 'unsecured',
    version: 1,
    name: 'Кредит без залога',
    short_description: 'Деньги на любые цели бизнеса',
    description_plain: '',
    purposes: ['working_capital'],
    facility: 'term_loan',
    repayment_options: ['annuity', 'differentiated'],
    amount_min: '300000.00',
    amount_max: '10000000.00',
    term_min_months: 3,
    term_max_months: 36,
    rate_base: '19.50',
    rate_max: '29.00',
    collateral_kind: 'none',
    collateral_required_from: null,
    collateral_types: [],
    guarantee: 'none',
    target_use_confirmation: false,
    support_program: null,
    min_business_age_months: 6,
    allowed_legal_forms: ['LLC', 'IE'],
    min_annual_revenue: null,
    required_documents: [
      { type: 'financial_report', title: 'Бухгалтерская отчётность', required_from_amount: '5000000.00', legal_forms: ['LLC', 'JSC'] },
      { type: 'tax_return', title: 'Налоговая декларация', required_from_amount: null, legal_forms: ['IE'] },
      { type: 'bank_statement', title: 'Выписка', required_from_amount: null, legal_forms: [] },
    ],
    application_fields_schema: {},
    workflow_code: 'credit_application_v1',
    auto_decision_limit: '5000000.00',
    status: 'active',
    keywords: ['без залога'],
    tag: 'Популярный',
    decision_time: null,
    ...overrides,
  }
}

describe('toCreditProduct', () => {
  it('переводит строки API в числа витрины', () => {
    const product = toCreditProduct(productDto())
    expect(product).toMatchObject({
      id: 'unsecured',
      code: 'UNSECURED',
      kind: 'lump-sum',
      title: 'Кредит без залога',
      rateFrom: 19.5,
      amount: { min: 300_000, max: 10_000_000 },
      termMonths: { min: 3, max: 36 },
      collateral: 'none',
      collateralRequiredFrom: null,
      startupOnly: false,
      tag: 'Популярный',
    })
    expect(product.requiredDocuments[0]).toEqual({
      type: 'financial_report',
      title: 'Бухгалтерская отчётность',
      requiredFrom: 5_000_000,
      legalForms: ['LLC', 'JSC'],
    })
  })

  it('кредитная линия и овердрафт — деньги частями', () => {
    expect(toCreditProduct(productDto({ facility: 'credit_line_revolving' })).kind).toBe('revolving')
    expect(toCreditProduct(productDto({ facility: 'overdraft' })).kind).toBe('revolving')
  })

  it('время решения не задано — по лимиту автоматики', () => {
    expect(toCreditProduct(productDto()).decisionTime).toBe('5 минут')
    // У ипотеки нет лимита авторешения (S-7): решает специалист
    expect(toCreditProduct(productDto({ auto_decision_limit: '0.00' })).decisionTime).toBe('1 рабочий день')
    expect(toCreditProduct(productDto({ decision_time: '15 минут' })).decisionTime).toBe('15 минут')
  })
})

describe('правила продукта — как у бэкенда при проверке комплектности', () => {
  it('залог: обязателен всегда или начиная с суммы', () => {
    const none = toCreditProduct(productDto())
    const required = toCreditProduct(productDto({ collateral_kind: 'required' }))
    const optional = toCreditProduct(productDto({ collateral_kind: 'optional', collateral_required_from: '5000000.00' }))
    expect(needsCollateral(none, 9_000_000)).toBe(false)
    expect(needsCollateral(required, 300_000)).toBe(true)
    expect(needsCollateral(optional, 4_999_999)).toBe(false)
    expect(needsCollateral(optional, 5_000_000)).toBe(true)
  })

  it('документы — по сумме и форме бизнеса', () => {
    const product = toCreditProduct(productDto())
    const types = (amount: number, form: string) => requiredDocumentsFor(product, amount, form).map((document) => document.type)
    expect(types(3_000_000, 'LLC')).toEqual(['bank_statement'])
    expect(types(5_000_000, 'LLC')).toEqual(['financial_report', 'bank_statement'])
    expect(types(5_000_000, 'IE')).toEqual(['tax_return', 'bank_statement'])
  })

  it('продукт доступен только своим формам бизнеса; пустой список — всем', () => {
    expect(isAvailableFor(toCreditProduct(productDto()), 'IE')).toBe(true)
    expect(isAvailableFor(toCreditProduct(productDto()), 'JSC')).toBe(false)
    expect(isAvailableFor(toCreditProduct(productDto({ allowed_legal_forms: [] })), 'JSC')).toBe(true)
  })

  it('доп. поля заявки есть, только если схема их описывает', () => {
    expect(hasProductFields(toCreditProduct(productDto()))).toBe(false)
    const mortgage = productDto({ application_fields_schema: { type: 'object', properties: { object_type: { type: 'string' } } } })
    expect(hasProductFields(toCreditProduct(mortgage))).toBe(true)
  })

  it('шаг ползунков: мелкий у небольших лимитов, крупный у больших', () => {
    expect(amountStep(toCreditProduct(productDto()))).toBe(50_000)
    expect(amountStep(toCreditProduct(productDto({ amount_max: '150000000.00' })))).toBe(100_000)
    expect(termStep(toCreditProduct(productDto()))).toBe(3)
    expect(termStep(toCreditProduct(productDto({ term_max_months: 12 })))).toBe(1)
  })
})
