import { describe, expect, it } from 'vitest'

import { toClientStatus } from './clientStatus'
import { clientStages } from './stages'
import { APPLICATION_STATUS_META, CLIENT_STATUS_META, CLOSED_CLIENT_STATUSES } from './status'

describe('toClientStatus — статус бэкенда глазами клиента', () => {
  it('на рассмотрении: проверка данных или оценка риска — по этапу процесса', () => {
    expect(toClientStatus('in_review', 'Проверяем данные компании')).toBe('checking')
    expect(toClientStatus('in_review', 'Оцениваем заявку')).toBe('scoring')
    expect(toClientStatus('in_review', 'Подбираем условия')).toBe('scoring')
    // S-3, S-6, S-7: заявка ушла андеррайтеру
    expect(toClientStatus('in_review', 'Заявка у специалиста')).toBe('scoring')
    expect(toClientStatus('in_review', null)).toBe('checking')
  })

  it('предложение: одобрено как просили или на других условиях', () => {
    expect(toClientStatus('offer_ready', null, 'as_requested')).toBe('approved')
    // S-2: встречное предложение андеррайтера на меньшую сумму
    expect(toClientStatus('offer_ready', null, 'counter')).toBe('counter_offer')
    expect(toClientStatus('offer_ready', null)).toBe('approved')
  })

  it('запрос информации, отказ, подписание и выдача', () => {
    expect(toClientStatus('info_requested', null)).toBe('info_requested')
    expect(toClientStatus('rejected', null)).toBe('rejected')
    expect(toClientStatus('signing', null)).toBe('signing')
    expect(toClientStatus('signed', null)).toBe('issued')
    expect(toClientStatus('disbursed', null)).toBe('issued')
  })

  it('закрытые без решения банка — своих статусов на этой шкале нет', () => {
    expect(toClientStatus('cancelled', null)).toBeNull()
    expect(toClientStatus('offer_declined', null)).toBeNull()
    expect(toClientStatus('expired', null)).toBeNull()
  })
})

describe('подписи статусов', () => {
  it('у каждого клиентского статуса есть подпись', () => {
    for (const meta of Object.values(CLIENT_STATUS_META)) expect(meta.label).not.toBe('')
    expect(CLIENT_STATUS_META.counter_offer.label).toBe('Другие условия')
    expect(CLIENT_STATUS_META.declined.label).toBe('Вы отказались')
  })

  it('закрытые статусы — по продукту можно подавать новую заявку', () => {
    expect(CLOSED_CLIENT_STATUSES).toEqual(expect.arrayContaining(['rejected', 'issued', 'cancelled', 'declined', 'expired']))
    expect(CLOSED_CLIENT_STATUSES).not.toContain('info_requested')
    expect(CLOSED_CLIENT_STATUSES).not.toContain('signing')
  })

  it('отказ выделен цветом бренда, одобрение — успехом, запрос данных — предупреждением', () => {
    expect(APPLICATION_STATUS_META.rejected.tone).toBe('brand')
    expect(APPLICATION_STATUS_META.approved.tone).toBe('success')
    expect(APPLICATION_STATUS_META.info_requested.tone).toBe('warning')
  })
})

describe('clientStages — шкала заявки клиента', () => {
  const states = (stages: ReturnType<typeof clientStages>) => stages.map((stage) => stage.state)

  it('черновик: заполняется, дальше всё впереди', () => {
    const stages = clientStages('draft', null)
    expect(stages[0]?.title).toBe('Заявка заполняется')
    expect(states(stages)).toEqual(['current', 'pending', 'pending'])
  })

  it('на проверке: подана, решение — текущий этап', () => {
    const stages = clientStages('scoring', '2026-10-26T09:00:00Z')
    expect(states(stages)).toEqual(['done', 'current', 'pending'])
    expect(stages[0]?.caption).toBe('26 окт., 12:00')
    expect(stages[1]?.caption).toBe('Оцениваем заявку, обычно до 5 минут')
  })

  it('запрос информации — решение ещё не принято', () => {
    expect(clientStages('info_requested', null)[1]).toMatchObject({ state: 'current', caption: 'Банк запросил дополнительные данные' })
  })

  it('одобрено и на иных условиях: решение пройдено, впереди подписание', () => {
    expect(clientStages('approved', null)[1]).toMatchObject({ state: 'done', caption: 'Одобрено' })
    expect(clientStages('counter_offer', null)[1]).toMatchObject({ state: 'done', caption: 'Банк предложил другие условия' })
    expect(states(clientStages('counter_offer', null))).toEqual(['done', 'done', 'current'])
  })

  it('отказ: остановились на решении банка', () => {
    expect(clientStages('rejected', null)[1]).toMatchObject({ state: 'current', caption: 'Банк отказал' })
  })

  it('кредит выдан: пройдены все этапы', () => {
    expect(states(clientStages('issued', null))).toEqual(['done', 'done', 'done'])
  })

  it('отменена — дальше подачи заявка не пошла', () => {
    expect(states(clientStages('cancelled', null))).toEqual(['done', 'pending', 'pending'])
  })
})
