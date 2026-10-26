import { describe, expect, it } from 'vitest'

import {
  formatDuration,
  formatMoney,
  formatMoneyShort,
  formatMoscowDateTime,
  formatPercent,
  formatProbability,
  formatRelativeTime,
  formatTerm,
  formatTermLimit,
  onlyDigits,
  pluralize,
} from './format'

/** Пробелы в числах сайт пишет неразрывными — в ожиданиях заменяем их обычными */
const plain = (text: string) => text.replace(/[\u00a0\u202f]/g, ' ')

describe('деньги и проценты', () => {
  it('formatMoney: разряды и знак рубля, копейки округляются', () => {
    expect(plain(formatMoney(3_000_000))).toBe('3 000 000 ₽')
    expect(plain(formatMoney(157_865.62))).toBe('157 866 ₽')
    expect(plain(formatMoney(0))).toBe('0 ₽')
  })

  it('formatMoney пишет разряды неразрывным пробелом — сумма не рвётся на строки', () => {
    expect(formatMoney(1_500_000)).toMatch(/^1[\u00a0\u202f]500[\u00a0\u202f]000 ₽$/)
  })

  it('formatMoneyShort: тысячи, миллионы, миллиарды', () => {
    expect(plain(formatMoneyShort(150_000_000))).toBe('150 млн ₽')
    expect(plain(formatMoneyShort(3_810_000))).toBe('3,8 млн ₽')
    expect(plain(formatMoneyShort(300_000))).toBe('300 тыс. ₽')
    expect(plain(formatMoneyShort(2_500_000_000))).toBe('2,5 млрд ₽')
    expect(plain(formatMoneyShort(999))).toBe('999 ₽')
  })

  it('formatPercent — до десятых, formatProbability — до сотых для PD', () => {
    expect(formatPercent(21.5)).toBe('21,5%')
    expect(formatPercent(17)).toBe('17%')
    expect(formatProbability(0.0421)).toBe('4,21%')
    expect(formatProbability(0.5)).toBe('50,00%')
  })
})

describe('сроки', () => {
  it('pluralize: один, два–четыре, пять и «-надцать»', () => {
    const forms = ['год', 'года', 'лет'] as const
    expect(pluralize(1, forms)).toBe('год')
    expect(pluralize(3, forms)).toBe('года')
    expect(pluralize(5, forms)).toBe('лет')
    expect(pluralize(11, forms)).toBe('лет')
    expect(pluralize(21, forms)).toBe('год')
    expect(pluralize(112, forms)).toBe('лет')
  })

  it('formatTerm: годы и месяцы', () => {
    expect(formatTerm(24)).toBe('2 года')
    expect(formatTerm(30)).toBe('2 года 6 мес.')
    expect(formatTerm(9)).toBe('9 месяцев')
    expect(formatTerm(12)).toBe('1 год')
    expect(formatTerm(120)).toBe('10 лет')
  })

  it('formatTermLimit: срок как предел', () => {
    expect(formatTermLimit(36)).toBe('до 3 лет')
    expect(formatTermLimit(12)).toBe('до 1 года')
    expect(formatTermLimit(18)).toBe('до 18 месяцев')
    expect(formatTermLimit(21)).toBe('до 21 месяца')
  })

  it('formatDuration: от секунд до дней', () => {
    expect(formatDuration(800)).toBe('< 1 с')
    expect(formatDuration(42_000)).toBe('42 с')
    expect(formatDuration(5 * 60_000)).toBe('5 мин')
    expect(formatDuration(3_900_000)).toBe('1 ч 5 мин')
    expect(formatDuration(2 * 3_600_000)).toBe('2 ч')
    expect(formatDuration((2 * 24 + 3) * 3_600_000)).toBe('2 дн. 3 ч')
    expect(formatDuration(24 * 3_600_000)).toBe('1 дн.')
  })
})

describe('даты', () => {
  it('formatMoscowDateTime — время подписи по Москве с пометкой МСК', () => {
    expect(formatMoscowDateTime('2026-10-24T09:35:53Z')).toBe('24.10.2026, 12:35:53 МСК')
  })

  it('formatRelativeTime: минуты, часы, дни', () => {
    const now = Date.parse('2026-10-26T12:00:00Z')
    expect(formatRelativeTime('2026-10-26T11:55:00Z', now)).toBe('5 минут назад')
    expect(formatRelativeTime('2026-10-26T09:00:00Z', now)).toBe('3 часа назад')
    expect(formatRelativeTime('2026-10-23T12:00:00Z', now)).toBe('3 дня назад')
    expect(formatRelativeTime('2026-10-26T17:00:00Z', now)).toBe('через 5 часов')
  })
})

describe('onlyDigits', () => {
  it('оставляет одни цифры', () => {
    expect(onlyDigits('1 500 000 ₽')).toBe('1500000')
    expect(onlyDigits('+7 (999) 123-45-67')).toBe('79991234567')
  })
})
