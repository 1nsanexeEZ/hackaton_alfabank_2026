import { mockCreditApi } from './mock'
import type { CreditApi } from './types'

/** API заявок на бэкенде ещё нет — работаем на моке в любом режиме */
export const creditApi: CreditApi = mockCreditApi

export { configureCreditMock } from './mock'
export { DEFAULT_SCORING_CONFIG, estimateRevenue, SCORING_FACTOR_LABEL, STOP_FACTOR_LABEL } from './scoring'
export { DOSSIERS, dossierInn, dossierName, dossierRegistrationDate, dossierStatus } from './sources'
export type * from './sources'
export type * from './types'
