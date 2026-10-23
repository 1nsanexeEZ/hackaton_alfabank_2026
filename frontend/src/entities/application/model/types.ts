import type { ApplicationStatus, ClientStatus, LoanPurpose } from '@/shared/api'

/** Статусы заявки описаны в контракте API; финальный набор фиксируем в стейт-машине (docs/state-machine.md) */
export type { ApplicationStatus }

/** Параметры кредита, которые клиент выбрал до отправки заявки */
export interface ApplicationDraft {
  productId: string
  amount: number
  termMonths: number
  /** Компания для заявки — когда клиент продолжает свой черновик; иначе мастер выберет сам */
  organizationId?: string
  /** Цель из черновика, который продолжают */
  purpose?: LoanPurpose
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
  /** Компания-заявитель; у примера на первом экране её нет */
  organizationName?: string | null
  /** null — в черновике ещё не указаны */
  amount: number | null
  termMonths: number | null
  status: ClientStatus
  stages: ApplicationStage[]
}
