import type { ClientApplicationCardDto, ClientStatus } from '@/shared/api'
import { pluralize } from '@/shared/lib'
import type { BadgeTone } from '@/shared/ui'

export type StepState = 'done' | 'current' | 'failed' | 'stopped' | 'todo'

export interface CardStep {
  label: string
  state: StepState
  /** Короткая подпись под этапом: «сейчас», «отказ», «вы отказались» */
  note: string
}

const STEP_LABELS = ['Подача', 'Проверка', 'Решение', 'Подписание', 'Выдача'] as const

/**
 * Где заявка на пути «Подача → Проверка → Решение → Подписание → Выдача».
 * Номер текущего этапа и его состояние; закрытые без выдачи заявки останавливаются на этапе,
 * где их закрыли: отказ банка — на решении, отказ клиента и истёкшее предложение — на подписании.
 */
function position(card: ClientApplicationCardDto): { index: number; state: StepState; note: string } {
  const status: ClientStatus = card.client_status
  switch (status) {
    case 'draft':
      return { index: 0, state: 'current', note: 'черновик' }
    case 'submitted':
    case 'checking':
    case 'scoring':
      return { index: 1, state: 'current', note: 'сейчас' }
    case 'info_requested':
      return { index: 1, state: 'current', note: 'нужны данные' }
    case 'approved':
    case 'counter_offer':
      return { index: 2, state: 'current', note: 'готово' }
    case 'rejected':
      return { index: 2, state: 'failed', note: 'отказ' }
    case 'signing':
      return { index: 3, state: 'current', note: 'сейчас' }
    case 'declined':
      return { index: 3, state: 'stopped', note: 'вы отказались' }
    case 'expired':
      return { index: 3, state: 'stopped', note: 'истекло' }
    case 'issued':
      return { index: 4, state: 'done', note: 'выдан' }
    case 'cancelled':
      return { index: card.offer ? 3 : card.submitted_at ? 1 : 0, state: 'stopped', note: 'отменена' }
  }
}

export function cardSteps(card: ClientApplicationCardDto): CardStep[] {
  const { index, state, note } = position(card)
  return STEP_LABELS.map((label, i) => ({
    label,
    state: i < index ? 'done' : i === index ? state : 'todo',
    note: i === index ? note : '',
  }))
}

/** Сколько дней осталось до конца предложения: «ещё 6 дней», «последний день»; null — уже истекло */
export function timeLeft(expiresAt: string, now = Date.now()): string | null {
  const ms = new Date(expiresAt).getTime() - now
  if (ms <= 0) return null
  const days = Math.floor(ms / 86_400_000)
  if (days === 0) return 'последний день'
  return `ещё ${days} ${pluralize(days, ['день', 'дня', 'дней'])}`
}

/** Цвета бейджа статуса на тёмной шапке окна: тот же смысл, что у BaseBadge, но читается на чёрном */
export const DARK_BADGE_CLASS: Record<BadgeTone, string> = {
  neutral: 'bg-night-glass text-on-night-secondary',
  brand: 'bg-brand/25 text-[#ff9d94]',
  success: 'bg-success/25 text-[#7fe0a6]',
  warning: 'bg-warning/30 text-[#ffc46b]',
  info: 'bg-info/30 text-[#9cc1ff]',
  glass: 'bg-night-glass text-on-night',
}
