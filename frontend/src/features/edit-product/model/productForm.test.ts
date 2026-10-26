import { describe, expect, it } from 'vitest'

import type { ProductDto } from '@/shared/api'

import { FACILITY_LOAN_TYPE, findProductCode, frontendIdOf, PRODUCT_CODES } from './productCodes'
import { splitKeywords, toCreateInput, toForm, toInput, validate, type ProductForm } from './productForm'

const mortgage = {
  code: 'MORTGAGE',
  frontend_id: 'mortgage',
  version: 3,
  name: 'Бизнес-ипотека',
  short_description: 'Офис, склад или производство в собственность',
  description_plain: 'Полное описание',
  purposes: ['real_estate'],
  facility: 'term_loan',
  repayment_options: ['annuity', 'differentiated'],
  amount_min: '3000000.00',
  amount_max: '150000000.00',
  term_min_months: 12,
  term_max_months: 120,
  rate_base: '18.50',
  rate_max: '26.00',
  collateral_kind: 'required',
  collateral_required_from: null,
  collateral_types: ['real_estate'],
  guarantee: 'owner',
  target_use_confirmation: true,
  support_program: null,
  min_business_age_months: 12,
  allowed_legal_forms: ['LLC', 'JSC', 'IE'],
  min_annual_revenue: '10000000.00',
  required_documents: [{ type: 'collateral_documents', title: 'Документы на залог', required_from_amount: null, legal_forms: [] }],
  application_fields_schema: { type: 'object', properties: { object_type: { type: 'string', enum: ['office'] } } },
  workflow_code: 'credit_application_v1',
  // У ипотеки нет лимита авторешения — всегда специалист (S-7)
  auto_decision_limit: '0.00',
  status: 'active',
  keywords: ['недвижимость', 'до 10 лет'],
  tag: null,
  decision_time: '1 рабочий день',
} satisfies ProductDto

const plain = (text: string) => text.replace(/[\u00a0\u202f]/g, ' ')

describe('форма продукта в рабочем месте', () => {
  it('из карточки: суммы с разрядами, ставки через запятую', () => {
    const form = toForm(mortgage)
    expect(plain(form.amountMax)).toBe('150 000 000')
    expect(form.rateBase).toBe('18,5')
    expect(form.autoDecisionLimit).toBe('0')
    expect(form.keywords).toBe('недвижимость, до 10 лет')
    expect(form.collateralKind).toBe('required')
  })

  it('новый продукт — пустая форма с разумными умолчаниями', () => {
    const form = toForm(null)
    expect(form).toMatchObject({ code: '', name: '', autoDecisionLimit: '0', facility: 'term_loan', legalForms: ['LLC', 'IE', 'JSC'] })
  })

  it('карточка без изменений проходит проверку', () => {
    expect(validate(toForm(mortgage), false)).toEqual({})
  })

  it('ловит ошибки условий', () => {
    const form: ProductForm = {
      ...toForm(mortgage),
      name: ' ',
      amountMin: '5 000 000',
      amountMax: '1 000 000',
      termMin: '0',
      rateBase: '30',
      rateMax: '20',
      purposes: [],
      keywords: 'один, два, три, четыре, пять, шесть',
      workflowCode: '',
    }
    expect(validate(form, false)).toEqual({
      name: 'Укажите название',
      amountMax: 'Не меньше суммы «от»',
      termMin: 'От 1 месяца',
      rateMax: 'Не ниже ставки «от» и до 100%',
      purposes: 'Хотя бы одна цель',
      keywords: 'Не больше 5 слов',
      workflowCode: 'Выберите маршрут',
    })
  })

  it('у нового продукта проверяет код и адрес карточки', () => {
    const fresh = { ...toForm(mortgage), code: '', frontendId: 'Mortgage!' }
    expect(validate(fresh, true)).toMatchObject({ code: 'Выберите код из справочника', frontendId: expect.any(String) })
    expect(validate({ ...fresh, code: 'EQUIPMENT', frontendId: 'equipment' }, true)).toEqual({})
  })

  it('PUT: изменённое из формы, остальное — из продукта как есть', () => {
    const input = toInput({ ...toForm(mortgage), amountMax: '200 000 000', rateBase: '17,25' }, mortgage)
    expect(input).toMatchObject({
      amount_max: '200000000',
      rate_base: '17.25',
      auto_decision_limit: '0',
      description_plain: 'Полное описание',
      required_documents: mortgage.required_documents,
      application_fields_schema: mortgage.application_fields_schema,
      min_annual_revenue: '10000000',
      collateral_required_from: null,
      tag: null,
    })
  })

  it('залог «по желанию» — порог обязательности из формы; без залога — типы залога пустые', () => {
    const optional = toInput({ ...toForm(mortgage), collateralKind: 'optional', collateralFrom: '5 000 000' }, mortgage)
    expect(optional.collateral_required_from).toBe('5000000')
    expect(toInput({ ...toForm(mortgage), collateralKind: 'none' }, mortgage).collateral_types).toEqual([])
  })

  it('создание: код и статус — черновик или сразу в продажу', () => {
    const form = { ...toForm(mortgage), code: ' EQUIPMENT ', frontendId: 'equipment' }
    expect(toCreateInput(form, null, false)).toMatchObject({ code: 'EQUIPMENT', status: 'draft', description_plain: '' })
    expect(toCreateInput(form, null, true).status).toBe('active')
  })

  it('короткие слова витрины — через запятую, пустые выкидываем', () => {
    expect(splitKeywords(' быстро, , без залога ,')).toEqual(['быстро', 'без залога'])
  })
})

describe('справочник кодов продукта', () => {
  it('первые девять — продукты каталога, коды не повторяются', () => {
    expect(PRODUCT_CODES.slice(0, 9).map((entry) => entry.code)).toEqual([
      'UNSECURED',
      'SECURED',
      'CREDIT_LINE',
      'OVERDRAFT',
      'AUTO',
      'MORTGAGE',
      'REFINANCE',
      'GOV_SUPPORT',
      'STARTUP',
    ])
    expect(new Set(PRODUCT_CODES.map((entry) => entry.code)).size).toBe(PRODUCT_CODES.length)
  })

  it('код задаёт вид выдачи и вид ссуды по форме 0409303', () => {
    const line = findProductCode('CREDIT_LINE')
    expect(line?.facility).toBe('credit_line_revolving')
    expect(FACILITY_LOAN_TYPE[line!.facility]).toBe('1.3')
    expect(FACILITY_LOAN_TYPE.overdraft).toBe('1.2')
    expect(findProductCode('NOPE')).toBeUndefined()
  })

  it('адрес карточки по коду', () => {
    expect(frontendIdOf('GOV_SUPPORT')).toBe('gov-support')
    expect(frontendIdOf('UNSECURED')).toBe('unsecured')
  })
})
