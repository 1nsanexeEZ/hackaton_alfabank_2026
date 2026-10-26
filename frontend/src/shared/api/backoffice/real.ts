import { http, httpFile, httpPage } from '../http'
import { decodeTicket, decodeTicketItem } from '../client/support'
import type { SupportTicketDto, SupportTicketListItemDto } from '../client/types'
import type { BackofficeApi, VersionDto, VersionsApi, VersionSummaryDto } from './types'

/** Карточка обращения с раскодированными темой и сообщениями */
const ticket = (path: string, options?: Parameters<typeof http>[1]) => http<SupportTicketDto>(path, options).then(decodeTicket)

/** Версии PD-модели и кредитной политики: одни и те же ручки под своим префиксом */
function versions<Catalog, Preview>(base: string): VersionsApi<Catalog, Preview> {
  const at = (version: string) => `${base}/${encodeURIComponent(version)}`
  return {
    list: () => http<VersionSummaryDto[]>(base),
    catalog: () => http<Catalog>(`${base}/catalog`),
    get: (version) => http<VersionDto>(at(version)),
    createDraft: (input) => http<VersionDto>(base, { method: 'POST', body: input }),
    updateDraft: (version, input) => http<VersionDto>(at(version), { method: 'PUT', body: input }),
    deleteDraft: (version) => http<void>(at(version), { method: 'DELETE' }),
    activate: (version) => http<VersionDto>(`${at(version)}/activate`, { method: 'POST' }),
    preview: (version, limit) => http<Preview>(`${at(version)}/preview`, { method: 'POST', query: { limit } }),
  }
}

/** Рабочее место андеррайтера: запросы подписываются токеном сотрудника */
export const backofficeApi: BackofficeApi = {
  queue: (query = {}) =>
    http('/bff/backoffice/queue', {
      query: { status: query.status, sort: query.sort, review: query.review, limit: query.limit, offset: query.offset },
    }),
  card: (applicationId) => http(`/bff/backoffice/applications/${applicationId}`),
  claim: (taskId) => http(`/tasks/${taskId}/claim`, { method: 'POST' }),
  complete: (taskId, input) => http(`/tasks/${taskId}/complete`, { method: 'POST', body: input }),
  metrics: (query = {}) => http('/bff/backoffice/metrics', { query: { date_from: query.dateFrom, date_to: query.dateTo } }),
  scoringOverview: (limit) => http('/bff/backoffice/scoring-overview', { query: { limit } }),
  applicationsOverview: (latest) => http('/bff/backoffice/applications-overview', { query: { latest } }),
  downloadDocument: (applicationId, documentId) => http(`/applications/${applicationId}/documents/${documentId}/download`),
  contractDocument: (applicationId, kind) => httpFile(`/applications/${applicationId}/contract/document`, { query: { kind } }),
  process: (applicationId) => http(`/processes/${applicationId}`),
  workflowDiagram: (code) => http(`/workflows/${code}/diagram`, { text: true }),
  applications: (query = {}) =>
    httpPage('/applications', {
      query: {
        organization_id: query.organizationId,
        status: query.status,
        decided_by: query.decidedBy,
        limit: query.limit,
        offset: query.offset,
      },
    }),
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
  supportQueue: (query = {}) =>
    httpPage<SupportTicketListItemDto>('/support/queue', {
      query: { status: query.status, scope: query.scope, limit: query.limit, offset: query.offset },
    }).then((page) => ({ ...page, items: page.items.map(decodeTicketItem) })),
  supportTicket: (id) => ticket(`/support/queue/${id}`),
  takeSupportTicket: (id) => ticket(`/support/queue/${id}/take`, { method: 'POST' }),
  releaseSupportTicket: (id) => ticket(`/support/queue/${id}/release`, { method: 'POST' }),
  replySupportTicket: (id, text) => ticket(`/support/queue/${id}/messages`, { method: 'POST', body: { text } }),
  resolveSupportTicket: (id) => ticket(`/support/queue/${id}/resolve`, { method: 'POST' }),
  closeSupportTicketByStaff: (id) => ticket(`/support/queue/${id}/close`, { method: 'POST' }),
  scoringModels: versions('/scoring/models'),
  decisionPolicies: versions('/decision/policies'),
}
