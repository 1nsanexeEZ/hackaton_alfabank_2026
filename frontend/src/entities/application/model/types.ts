import type { ClientStatus, LoanPurpose } from '@/shared/api'

/** Этап заявки для клиента — client_status без закрытых без решения банка (docs/state-machine.md) */
export type ApplicationStatus = Exclude<ClientStatus, 'cancelled' | 'declined' | 'expired'>

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
