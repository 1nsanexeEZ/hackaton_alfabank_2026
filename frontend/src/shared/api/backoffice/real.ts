import { http, httpFile } from '../http'
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
  contractDocument: (applicationId, kind) => httpFile(`/applications/${applicationId}/contract/document`, { query: { kind } }),
  process: (applicationId) => http(`/processes/${applicationId}`),
  workflowDiagram: (code) => http(`/workflows/${code}/diagram`, { text: true }),
  applications: (query = {}) => http('/applications', { query: { limit: query.limit, offset: query.offset } }),
  organizations: () => http('/organizations'),
  organization: (organizationId) => http(`/organizations/${organizationId}`),
  preApprovedOffers: (organizationId) => http(`/organizations/${organizationId}/pre-approved-offers`),
  founderPrescreen: (organizationId) => http(`/organizations/${organizationId}/founder-prescreen`),
  projectAssessment: (organizationId) => http(`/organizations/${organizationId}/project-assessment`),
  businessPlan: (organizationId) => http(`/organizations/${organizationId}/business-plan`),
  products: (scope) => http(scope === 'all' ? '/products/all' : '/products'),
  createProduct: (input) => http('/products', { method: 'POST', body: input }),
  updateProduct: (code, input) => http(`/products/${code}`, { method: 'PUT', body: input }),
  activateProduct: (code) => http(`/products/${code}/activate`, { method: 'POST' }),
  withdrawProduct: (code) => http(`/products/${code}`, { method: 'DELETE' }),
  workflows: () => http('/workflows'),
  innCheck: (input) => http('/organizations/inn-check', { method: 'POST', body: input }),
}
