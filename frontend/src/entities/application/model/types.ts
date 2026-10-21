import type { ApplicationStatus } from '@/shared/api'

/** Статусы заявки описаны в контракте API; финальный набор фиксируем в стейт-машине (docs/state-machine.md) */
export type { ApplicationStatus }

/** Параметры кредита, которые клиент выбрал до отправки заявки */
export interface ApplicationDraft {
  productId: string
  amount: number
  termMonths: number
}

export type StageState = 'done' | 'current' | 'pending'

export interface ApplicationStage {
  title: string
  caption?: string
  state: StageState
}

export interface ApplicationPreview {
  number: string
  productTitle: string
  amount: number
  termMonths: number
  status: ApplicationStatus
  stages: ApplicationStage[]
}
