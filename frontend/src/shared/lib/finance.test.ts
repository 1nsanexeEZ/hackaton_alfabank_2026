import { describe, expect, it } from 'vitest'

import { calcAnnuityPayment, calcLoanSummary, clamp } from './finance'

describe('calcAnnuityPayment', () => {
  it('считает аннуитет по формуле: 3 млн на 24 месяца под 23,5% годовых', () => {
    // S-1: одобрение «Ромашки» — 3 000 000 ₽ / 24 мес. / 23,50%
    expect(calcAnnuityPayment(3_000_000, 23.5, 24)).toBeCloseTo(157_865.62, 2)
  })

  it('без процентов делит сумму поровну', () => {
    expect(calcAnnuityPayment(1_200_000, 0, 12)).toBe(100_000)
  })

  it('нулевая сумма или срок — платежа нет', () => {
    expect(calcAnnuityPayment(0, 20, 12)).toBe(0)
    expect(calcAnnuityPayment(1_000_000, 20, 0)).toBe(0)
    expect(calcAnnuityPayment(-5, 20, 12)).toBe(0)
  })

  it('чем длиннее срок, тем меньше платёж', () => {
    expect(calcAnnuityPayment(5_000_000, 20, 60)).toBeLessThan(calcAnnuityPayment(5_000_000, 20, 24))
  })
})

describe('calcLoanSummary', () => {
  it('сумма выплат — платёж на срок, переплата — сверх долга', () => {
    const summary = calcLoanSummary(3_000_000, 23.5, 24)
    expect(summary.totalPayment).toBeCloseTo(summary.monthlyPayment * 24, 6)
    expect(summary.overpayment).toBeCloseTo(summary.totalPayment - 3_000_000, 6)
    expect(summary.overpayment).toBeGreaterThan(0)
  })

  it('без процентов переплаты нет', () => {
    expect(calcLoanSummary(1_200_000, 0, 12)).toEqual({ monthlyPayment: 100_000, totalPayment: 1_200_000, overpayment: 0 })
  })
})

describe('clamp', () => {
  it('держит значение в пределах', () => {
    expect(clamp(5, 1, 10)).toBe(5)
    expect(clamp(-1, 1, 10)).toBe(1)
    expect(clamp(11, 1, 10)).toBe(10)
  })
})
