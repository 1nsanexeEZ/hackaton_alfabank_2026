import type { ClientStatus } from '@/shared/api'
import { formatDateTime } from '@/shared/lib'

import type { ApplicationStage } from './types'

const STAGE_TITLES = ['Заявка отправлена', 'Проверка данных', 'Оценка риска', 'Решение банка', 'Подписание и выдача']

type Progress = { current: number; caption?: string; decision?: string }

/** Где заявка на шкале и что подписать у текущего этапа; current = длина шкалы — всё пройдено */
const PROGRESS: Partial<Record<ClientStatus, Progress>> = {
  submitted: { current: 1, caption: 'ЕГРЮЛ, ФНС, бюро кредитных историй' },
  checking: { current: 1, caption: 'ЕГРЮЛ, ФНС, бюро кредитных историй' },
  scoring: { current: 2, caption: 'Обычно до 5 минут' },
  info_requested: { current: 2, caption: 'Банк запросил дополнительные данные' },
  approved: { current: 4, caption: 'Примите предложение и подпишите договор', decision: 'Одобрено' },
  counter_offer: { current: 4, caption: 'Примите предложение и подпишите договор', decision: 'Банк предложил другие условия' },
  rejected: { current: 3, caption: 'Банк отказал' },
  signing: { current: 4, caption: 'Подпишите договор', decision: 'Одобрено' },
  issued: { current: 5, decision: 'Одобрено' },
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
    if (index === 3) return { title, caption: decision, state: 'done' }
    return { title, state: 'done' }
  })
}
