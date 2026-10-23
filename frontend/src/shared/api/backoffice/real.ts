import { http } from '../http'
import type { BackofficeApi } from './types'

/** Рабочее место андеррайтера: запросы подписываются токеном сотрудника */
export const backofficeApi: BackofficeApi = {
  queue: (query = {}) =>
    http('/bff/backoffice/queue', {
      query: { status: query.status, sort: query.sort, limit: query.limit, offset: query.offset },
    }),
  card: (applicationId) => http(`/bff/backoffice/applications/${applicationId}`),
  claim: (taskId) => http(`/tasks/${taskId}/claim`, { method: 'POST' }),
  complete: (taskId, input) => http(`/tasks/${taskId}/complete`, { method: 'POST', body: input }),
  metrics: (query = {}) => http('/bff/backoffice/metrics', { query: { date_from: query.dateFrom, date_to: query.dateTo } }),
  downloadDocument: (applicationId, documentId) => http(`/applications/${applicationId}/documents/${documentId}/download`),
}
