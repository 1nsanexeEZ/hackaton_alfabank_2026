import { describe, expect, it } from 'vitest'

import type { ClientApplicationCardDto, ClientStatus } from '@/shared/api'

import { cardSteps, timeLeft } from './presentation'

const card = (client_status: ClientStatus, extra: Partial<ClientApplicationCardDto> = {}) =>
  ({ client_status, offer: null, submitted_at: null, ...extra }) as unknown as ClientApplicationCardDto

/** Этапы «Подача → Проверка → Решение → Подписание → Выдача» одной строкой: состояние/подпись */
const line = (status: ClientStatus, extra?: Partial<ClientApplicationCardDto>) =>
  cardSteps(card(status, extra)).map((step) => (step.note ? `${step.state}:${step.note}` : step.state))

describe('cardSteps — путь заявки в окне клиента', () => {
  it('черновик и проверка', () => {
    expect(line('draft')).toEqual(['current:черновик', 'todo', 'todo', 'todo', 'todo'])
    expect(line('scoring')).toEqual(['done', 'current:сейчас', 'todo', 'todo', 'todo'])
  })

  it('запрос информации — на проверке, «нужны данные»', () => {
    expect(line('info_requested')).toEqual(['done', 'current:нужны данные', 'todo', 'todo', 'todo'])
  })

  it('одобрено и встречное предложение — решение готово', () => {
    expect(line('approved')).toEqual(['done', 'done', 'current:готово', 'todo', 'todo'])
    expect(line('counter_offer')).toEqual(['done', 'done', 'current:готово', 'todo', 'todo'])
  })

  it('отказ — красный этап решения', () => {
    expect(line('rejected')).toEqual(['done', 'done', 'failed:отказ', 'todo', 'todo'])
  })

  it('подписание и выдача', () => {
    expect(line('signing')).toEqual(['done', 'done', 'done', 'current:сейчас', 'todo'])
    expect(line('issued')).toEqual(['done', 'done', 'done', 'done', 'done:выдан'])
  })

  it('отказ клиента и истёкшее предложение останавливаются на подписании', () => {
    expect(line('declined')[3]).toBe('stopped:вы отказались')
    expect(line('expired')[3]).toBe('stopped:истекло')
  })

  it('отменённая — там, где её закрыли', () => {
    expect(line('cancelled')[0]).toBe('stopped:отменена')
    expect(line('cancelled', { submitted_at: '2026-10-26T09:00:00Z' })[1]).toBe('stopped:отменена')
    expect(line('cancelled', { offer: {} as ClientApplicationCardDto['offer'] })[3]).toBe('stopped:отменена')
  })
})

describe('timeLeft — срок предложения', () => {
  const now = Date.parse('2026-10-26T12:00:00Z')

  it('дни до конца', () => {
    expect(timeLeft('2026-11-01T13:00:00Z', now)).toBe('ещё 6 дней')
    expect(timeLeft('2026-10-28T12:30:00Z', now)).toBe('ещё 2 дня')
    expect(timeLeft('2026-10-27T13:00:00Z', now)).toBe('ещё 1 день')
  })

  it('меньше суток — последний день, прошло — null', () => {
    expect(timeLeft('2026-10-26T20:00:00Z', now)).toBe('последний день')
    expect(timeLeft('2026-10-26T11:00:00Z', now)).toBeNull()
  })
})
