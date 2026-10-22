import { ApiError, http } from '../http'
import type { ClientApi } from './types'

type Options = NonNullable<Parameters<typeof http>[1]>

/** Запросы сайта подписываются токеном клиента — сессия сотрудника сюда не попадает */
const call = <T>(path: string, options: Options = {}) => http<T>(path, { ...options, realm: 'client' })

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
  cancelApplication: (id) => call(`/applications/${id}/cancel`, { method: 'POST' }),

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
