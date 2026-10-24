import { ApiError, http, httpFile } from '../http'
import type { ClientApi } from './types'

type Options = NonNullable<Parameters<typeof http>[1]>

/** Запросы сайта подписываются токеном клиента — сессия сотрудника сюда не попадает */
const call = <T>(path: string, options: Options = {}) => http<T>(path, { ...options, realm: 'client' })

/** Проверяемый файл — полем file в multipart/form-data */
function fileForm(file: File): FormData {
  const form = new FormData()
  form.append('file', file)
  return form
}

/** Клиентский путь на бэкенде: auth, products, organizations, applications */
export const realClientApi: ClientApi = {
  login: (login, password) => call('/auth/login', { method: 'POST', body: { login, password } }),
  demoAccounts: () => call('/auth/demo-accounts'),
  demoLogin: (login) => call('/auth/demo-login', { method: 'POST', body: { login } }),
  me: () => call('/me'),
  listProducts: () => call('/products'),
  calculate: (code, input) => call(`/products/${code}/calculate`, { method: 'POST', body: input }),
  eligibility: (code, organizationId) =>
    call(`/products/${code}/eligibility`, { query: { organization_id: organizationId } }),
  listOrganizations: () => call('/organizations'),
  listApplications: (limit) => call('/applications', { query: { limit } }),
  createApplication: (organizationId, productCode) =>
    call('/applications', { method: 'POST', body: { organization_id: organizationId, product_code: productCode } }),
  getApplication: (id) => call(`/applications/${id}`),
  updateApplication: (id, input) => call(`/applications/${id}`, { method: 'PATCH', body: input }),
  completeness: (id) => call(`/applications/${id}/completeness`),
  requestDocumentUpload: (id, input) => call(`/applications/${id}/documents`, { method: 'POST', body: input }),
  confirmDocument: (id, documentId) =>
    call(`/applications/${id}/documents/${documentId}/confirm`, { method: 'POST' }),
  deleteDocument: (id, documentId) => call(`/applications/${id}/documents/${documentId}`, { method: 'DELETE' }),
  submitApplication: (id) => call(`/applications/${id}/submit`, { method: 'POST' }),
  cancelApplication: (id, reason) =>
    call(`/applications/${id}/cancel`, { method: 'POST', body: reason ? { reason } : undefined }),

  dashboard: (organizationId) => call('/bff/dashboard', { query: { organization_id: organizationId } }),
  listApplicationRows: (organizationId, limit = 50) =>
    call('/bff/applications', { query: { organization_id: organizationId, limit } }),
  getApplicationCard: (id) => call(`/bff/applications/${id}`),
  acceptOffer: (id) => call(`/applications/${id}/offer/accept`, { method: 'POST' }),
  declineOffer: (id, reason) =>
    call(`/applications/${id}/offer/decline`, { method: 'POST', body: reason ? { reason } : undefined }),
  contract: (id) => call(`/applications/${id}/contract`),
  // Поля без значения JSON.stringify отбрасывает: старому бэкенду уходит прежнее тело
  sign: (id, password, offerHash, documentHash, rulesVersion) =>
    call(`/applications/${id}/sign`, {
      method: 'POST',
      body: { password, offer_hash: offerHash, document_hash: documentHash, rules_version: rulesVersion },
    }),
  downloadContractDocument: (id, kind) =>
    httpFile(`/applications/${id}/contract/document`, { query: { kind }, realm: 'client' }),
  esignRules: () => call('/esign/rules'),
  verifyContract: (documentId) => call(`/contracts/verify/${documentId}`),
  verifyContractFile: (file) => call('/contracts/verify', { method: 'POST', body: fileForm(file) }),
  answerInfoRequest: (id, infoRequestId) =>
    call(`/applications/${id}/info-requests/${infoRequestId}/answer`, { method: 'POST' }),
  downloadDocument: (id, documentId) => call(`/applications/${id}/documents/${documentId}/download`),

  recommend: (need) => call('/products/recommend', { method: 'POST', body: need }),
  recommendFor: (need, organizationId) =>
    call('/bff/products/recommend', {
      query: { purpose: need.purpose, amount: need.amount, term_months: need.term_months, organization_id: organizationId },
    }),

  feed: (query = {}) =>
    call('/feed', {
      query: {
        organization_id: query.organizationId,
        application_id: query.applicationId,
        unread_only: query.unreadOnly ? 'true' : undefined,
        limit: query.limit,
        offset: query.offset,
      },
    }),
  unreadCount: () => call('/feed/unread-count'),
  readFeedItem: (itemId) => call(`/feed/${itemId}/read`, { method: 'POST' }),
  readAllFeed: () => call('/feed/read-all', { method: 'POST' }),
  streamTicket: () => call('/feed/stream-ticket', { method: 'POST' }),
  news: (organizationId, limit) => call('/news', { query: { organization_id: organizationId, limit } }),
  readNews: (newsId) => call(`/news/${newsId}/read`, { method: 'POST' }),

  getOrganization: (id) => call(`/organizations/${id}`),
  financialReports: (organizationId) => call(`/organizations/${organizationId}/financial-reports`),
  submitFinancialReport: (organizationId, input) =>
    call(`/organizations/${organizationId}/financial-reports`, { method: 'POST', body: input }),
  preApprovedOffers: (organizationId) => call(`/organizations/${organizationId}/pre-approved-offers`),
  members: (organizationId) => call(`/organizations/${organizationId}/members`),
  addMember: (organizationId, login, role) =>
    call(`/organizations/${organizationId}/members`, { method: 'POST', body: { login, role } }),
  grantPowerOfAttorney: (organizationId, accountId, input) =>
    call(`/organizations/${organizationId}/members/${accountId}/poa`, { method: 'POST', body: input }),
  changeMemberRole: (organizationId, accountId, role) =>
    call(`/organizations/${organizationId}/members/${accountId}`, { method: 'PATCH', body: { role } }),
  removeMember: (organizationId, accountId) =>
    call(`/organizations/${organizationId}/members/${accountId}`, { method: 'DELETE' }),
  verifyOrganization: (organizationId) => call(`/organizations/${organizationId}/verification`, { method: 'POST' }),
  updateProfile: (input) => call('/me/profile', { method: 'PATCH', body: input }),

  consents: () => call('/me/consents'),
  giveConsents: (types) => call('/me/consents', { method: 'POST', body: { types } }),
  revokeConsent: (type) => call(`/me/consents/${type}`, { method: 'DELETE' }),

  calculateFor: (code, organizationId, input) =>
    call(`/bff/products/${code}/calculate`, { method: 'POST', query: { organization_id: organizationId }, body: input }),

  runFounderPrescreen: (organizationId) => call(`/organizations/${organizationId}/founder-prescreen`, { method: 'POST' }),
  founderPrescreen: (organizationId) => call(`/organizations/${organizationId}/founder-prescreen`),
  organizationConsents: (organizationId) => call(`/organizations/${organizationId}/consents`),
  giveOrganizationConsents: (organizationId, types) =>
    call(`/organizations/${organizationId}/consents`, { method: 'POST', body: { types } }),
  revokeOrganizationConsent: (organizationId, type) =>
    call(`/organizations/${organizationId}/consents/${type}`, { method: 'DELETE' }),
  businessPlan: (organizationId) => call(`/organizations/${organizationId}/business-plan`),
  submitBusinessPlan: (organizationId, input) =>
    call(`/organizations/${organizationId}/business-plan`, { method: 'PUT', body: input }),
  projectAssessment: (organizationId) => call(`/organizations/${organizationId}/project-assessment`),
  runProjectAssessment: (organizationId) => call(`/organizations/${organizationId}/project-assessment`, { method: 'POST' }),

  async uploadFile(upload, file) {
    let response: Response
    try {
      // Ссылка подписана хранилищем: заголовки и метод берём ровно из ответа бэкенда
      response = await fetch(upload.url, { method: upload.method, headers: upload.headers, body: file })
    } catch {
      throw new ApiError(0, 'network_error', 'Не удалось загрузить файл: хранилище недоступно')
    }
    if (!response.ok) {
      throw new ApiError(response.status, 'upload_failed', 'Хранилище не приняло файл, попробуйте ещё раз')
    }
  },
}
