import { describe, expect, it } from 'vitest'

import { groupThousands, inputModeFor, parseNumber, sanitizeInput } from './input'

const NBSP = '\u00a0'

describe('parseNumber', () => {
  it('читает суммы и проценты так, как их пишет сайт', () => {
    expect(parseNumber(`3${NBSP}000${NBSP}000 ₽`)).toBe(3_000_000)
    expect(parseNumber('3000000.00')).toBe(3_000_000)
    expect(parseNumber('23,5 %')).toBe(23.5)
    expect(parseNumber('-150 000')).toBe(-150_000)
  })

  it('без цифр — null', () => {
    expect(parseNumber('')).toBeNull()
    expect(parseNumber('₽')).toBeNull()
  })
})

describe('groupThousands', () => {
  it('ставит неразрывный пробел между разрядами', () => {
    expect(groupThousands('3000000')).toBe(`3${NBSP}000${NBSP}000`)
    expect(groupThousands('999')).toBe('999')
  })
})

describe('sanitizeInput', () => {
  it('digits — только цифры', () => {
    expect(sanitizeInput('77-01 15a', 'digits')).toBe('770115')
  })

  it('amount — вставка суммы с рублём и копейками даёт целые рубли с разрядами', () => {
    expect(sanitizeInput('3 000 000 ₽', 'amount')).toBe(`3${NBSP}000${NBSP}000`)
    expect(sanitizeInput('3000000.00', 'amount')).toBe(`3${NBSP}000${NBSP}000`)
    expect(sanitizeInput('007', 'amount')).toBe('7')
  })

  it('signedAmount — минус только в начале, любое тире считается минусом', () => {
    expect(sanitizeInput('−150000', 'signedAmount')).toBe(`-150${NBSP}000`)
    expect(sanitizeInput('15-0000', 'signedAmount')).toBe(`150${NBSP}000`)
    expect(sanitizeInput('150000', 'signedAmount')).toBe(`150${NBSP}000`)
  })

  it('decimal — один разделитель-запятая и не больше двух знаков после', () => {
    expect(sanitizeInput('23.567', 'decimal')).toBe('23,56')
    expect(sanitizeInput('1,2,3', 'decimal')).toBe('1,23')
    expect(sanitizeInput('12%', 'decimal')).toBe('12')
  })

  it('phone — плюс только первым, скобки и дефисы остаются', () => {
    expect(sanitizeInput('+7 (999) 123-45-67', 'phone')).toBe('+7 (999) 123-45-67')
    expect(sanitizeInput('8+999abc', 'phone')).toBe('8999')
  })
})

describe('inputModeFor', () => {
  it('выбирает клавиатуру телефона под поле', () => {
    expect(inputModeFor('phone')).toBe('tel')
    expect(inputModeFor('decimal')).toBe('decimal')
    expect(inputModeFor('amount')).toBe('numeric')
    expect(inputModeFor('digits')).toBe('numeric')
    expect(inputModeFor('signedAmount')).toBe('text')
  })
})
