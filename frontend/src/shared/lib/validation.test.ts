import { describe, expect, it } from 'vitest'

import { isValidInn } from './validation'

describe('isValidInn', () => {
  it('принимает ИНН демо-компаний: юрлица из 10 цифр и ИП из 12', () => {
    // backend/seed/demo_data.py: «Ромашка», ИП Иванов, «Сбой»
    expect(isValidInn('7701158817')).toBe(true)
    expect(isValidInn('770669871605')).toBe(true)
    expect(isValidInn('7705729405')).toBe(true)
  })

  it('ловит ошибку в контрольном разряде', () => {
    expect(isValidInn('7701158818')).toBe(false)
    expect(isValidInn('770669871606')).toBe(false)
    expect(isValidInn('770669871615')).toBe(false)
  })

  it('не принимает другую длину, буквы и пробелы', () => {
    expect(isValidInn('')).toBe(false)
    expect(isValidInn('770115881')).toBe(false)
    expect(isValidInn('77011588170')).toBe(false)
    expect(isValidInn('77011588a7')).toBe(false)
    expect(isValidInn(' 7701158817')).toBe(false)
  })
})
