/**
 * Статусы заявки — черновой список для витрины.
 * Финальный набор и переходы фиксируем в стейт-машине (docs/state-machine.md) и синхронизируем с бэкендом.
 */
export type ApplicationStatus =
  | 'draft'
  | 'submitted'
  | 'checking'
  | 'scoring'
  | 'info_requested'
  | 'approved'
  | 'counter_offer'
  | 'rejected'
  | 'signing'
  | 'issued'

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
