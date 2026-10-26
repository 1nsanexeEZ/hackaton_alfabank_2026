import { describe, expect, it } from 'vitest'

import { reportFormErrors, reportPeriod, toReportInput, type ReportForm } from './financialReport'
import { normalizePoaNumber, POA_NUMBER_HINT, poaNumberError } from './useCompany'

const report = (overrides: Partial<ReportForm> = {}): ReportForm => ({
  year: '2025',
  quarter: '',
  revenue: '36 000 000',
  expenses: '',
  netProfit: '',
  liabilities: '',
  debtPayments: '',
  ...overrides,
})

describe('отчётность компании: форма отчёта', () => {
  it('заполнена верно — ошибок нет, суммы уходят числами', () => {
    const form = report({ quarter: '2', expenses: '30 000 000', netProfit: '-1 500 000', debtPayments: '250 000' })
    expect(reportFormErrors(form, 2026)).toEqual({})
    expect(toReportInput(form)).toEqual({
      period_year: 2025,
      period_quarter: 2,
      revenue: 36_000_000,
      expenses: 30_000_000,
      net_profit: -1_500_000,
      total_liabilities: null,
      monthly_debt_payments: 250_000,
    })
  })

  it('год — с 2000 по текущий, отчёта за будущий год нет', () => {
    expect(reportFormErrors(report({ year: '2027' }), 2026).year).toBe('Укажите год')
    expect(reportFormErrors(report({ year: '1999' }), 2026).year).toBe('Укажите год')
    expect(reportFormErrors(report({ year: '' }), 2026).year).toBe('Укажите год')
    expect(reportFormErrors(report({ year: '2026' }), 2026).year).toBeUndefined()
  })

  it('выручка обязательна; ноль — можно', () => {
    expect(reportFormErrors(report({ revenue: '' }), 2026).revenue).toBe('Укажите выручку')
    expect(reportFormErrors(report({ revenue: '0' }), 2026)).toEqual({})
  })

  it('прибыль не больше выручки, убыток — со знаком минус', () => {
    expect(reportFormErrors(report({ revenue: '1 000 000', netProfit: '1 000 001' }), 2026).netProfit).toBe('Не больше выручки')
    expect(reportFormErrors(report({ revenue: '1 000 000', netProfit: '-5 000 000' }), 2026)).toEqual({})
  })

  it('необязательные поля — числа или пусто', () => {
    expect(reportFormErrors(report({ liabilities: 'много' }), 2026).liabilities).toBe('Введите число')
  })

  it('период: квартал или год целиком', () => {
    expect(reportPeriod({ period_year: 2025, period_quarter: 2 })).toBe('2 кв. 2025')
    expect(reportPeriod({ period_year: 2025, period_quarter: null })).toBe('2025 год')
  })
})

describe('доверенность на подпись — номер как проверяет бэкенд', () => {
  it('знак № и лишние пробелы убираем', () => {
    expect(normalizePoaNumber('  №  77 АБ   1234567 ')).toBe('77 АБ 1234567')
  })

  it('подходят буквы и цифры с разделителями, хотя бы одна цифра', () => {
    expect(poaNumberError('77 АБ 1234567')).toBeNull()
    expect(poaNumberError('№ 12/2026-Д')).toBeNull()
    expect(poaNumberError('Д.15')).toBeNull()
  })

  it('пусто — просим указать', () => {
    expect(poaNumberError('  № ')).toBe('Укажите номер доверенности')
  })

  it('без цифр, с запрещёнными знаками, разделителем по краю или длиннее 32 знаков — подсказка формата', () => {
    expect(poaNumberError('Доверенность')).toBe(POA_NUMBER_HINT)
    expect(poaNumberError('12#34')).toBe(POA_NUMBER_HINT)
    expect(poaNumberError('/1234')).toBe(POA_NUMBER_HINT)
    expect(poaNumberError('1234-')).toBe(POA_NUMBER_HINT)
    expect(poaNumberError('1'.repeat(33))).toBe(POA_NUMBER_HINT)
    expect(poaNumberError('1'.repeat(32))).toBeNull()
  })
})
