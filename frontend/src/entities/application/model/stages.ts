import type { ClientStatus } from '@/shared/api'
import { formatDateTime } from '@/shared/lib'

import type { ApplicationStage } from './types'

// Проверку данных и оценку риска клиенту отдельными этапами не показываем — это подпись у «Решения банка»
const STAGE_TITLES = ['Заявка отправлена', 'Решение банка', 'Подписание и выдача']

const DECISION_INDEX = 1

type Progress = { current: number; caption?: string; decision?: string }

/** Где заявка на шкале и что подписать у текущего этапа; current = длина шкалы — всё пройдено */
const PROGRESS: Partial<Record<ClientStatus, Progress>> = {
  submitted: { current: 1, caption: 'Проверяем данные в ЕГРЮЛ, ФНС и бюро кредитных историй' },
  checking: { current: 1, caption: 'Проверяем данные в ЕГРЮЛ, ФНС и бюро кредитных историй' },
  scoring: { current: 1, caption: 'Оцениваем заявку, обычно до 5 минут' },
  info_requested: { current: 1, caption: 'Банк запросил дополнительные данные' },
  approved: { current: 2, caption: 'Примите предложение и подпишите договор', decision: 'Одобрено' },
  counter_offer: { current: 2, caption: 'Примите предложение и подпишите договор', decision: 'Банк предложил другие условия' },
  rejected: { current: 1, caption: 'Банк отказал' },
  signing: { current: 2, caption: 'Подпишите договор', decision: 'Одобрено' },
  issued: { current: 3, decision: 'Одобрено' },
}

/** Шкала этапов настоящей заявки клиента — та же, что в примере на первом экране */
export function clientStages(status: ClientStatus, submittedAt: string | null): ApplicationStage[] {
  if (status === 'draft') {
    return [
      { title: 'Заявка заполняется', caption: 'Черновик сохранён — можно продолжить', state: 'current' },
      ...STAGE_TITLES.slice(1).map((title) => ({ title, state: 'pending' as const })),
    ]
  }
  const submitted = submittedAt ? formatDateTime(submittedAt) : undefined
  const progress = PROGRESS[status]
  // Отменена, отказ от предложения, истекла — заявка закрыта без следующего шага
  if (!progress) {
    return STAGE_TITLES.map((title, index) => ({ title, caption: index ? undefined : submitted, state: index ? 'pending' : 'done' }))
  }
  const { current, caption, decision } = progress
  return STAGE_TITLES.map((title, index) => {
    if (index === current) return { title, caption, state: 'current' }
    if (index > current) return { title, state: 'pending' }
    if (index === 0) return { title, caption: submitted, state: 'done' }
    if (index === DECISION_INDEX) return { title, caption: decision, state: 'done' }
    return { title, state: 'done' }
  })
}
