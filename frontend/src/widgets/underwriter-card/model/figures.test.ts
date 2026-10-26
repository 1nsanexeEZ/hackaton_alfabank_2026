import { describe, expect, it } from 'vitest'

import { amount, change, millions, monthLabel, niceCeil, share } from './figures'

describe('числа карточки андеррайтера', () => {
  it('amount: строка API → число, пусто — null', () => {
    expect(amount('3000000.00')).toBe(3_000_000)
    expect(amount(42)).toBe(42)
    expect(amount('')).toBeNull()
    expect(amount(null)).toBeNull()
    expect(amount(undefined)).toBeNull()
  })

  it('millions: таблицы в млн ₽', () => {
    expect(millions(48_000_000)).toBe('48,0')
    expect(millions(380_000)).toBe('0,38')
    expect(millions(-1_250_000)).toBe('-1,3')
    expect(millions(0)).toBe('0')
  })

  it('change: изменение к прошлому периоду со знаком', () => {
    expect(change(109, 100)).toEqual({ text: '+9%', sign: 1 })
    expect(change(90, 100)).toEqual({ text: '−10%', sign: -1 })
    expect(change(100, 100)).toEqual({ text: '0%', sign: 0 })
    // Убыток уменьшился — это рост
    expect(change(-50, -100)).toEqual({ text: '+50%', sign: 1 })
    expect(change(100, 0)).toBeNull()
    expect(change(100, null)).toBeNull()
  })

  it('niceCeil: верх оси с запасом', () => {
    expect(niceCeil(4_260_000)).toBe(5_000_000)
    expect(niceCeil(1.3)).toBe(1.5)
    expect(niceCeil(100)).toBe(100)
    expect(niceCeil(0)).toBe(1)
  })

  it('monthLabel: месяц выписки', () => {
    expect(monthLabel('2025-10')).toBe('окт')
    expect(monthLabel('2026-01', true)).toBe('янв 26')
  })

  it('share: доля для полосы в пределах 0–100', () => {
    expect(share(1, 4)).toBe(25)
    expect(share(5, 4)).toBe(100)
    expect(share(-1, 4)).toBe(0)
    expect(share(1, 0)).toBe(0)
  })
})
