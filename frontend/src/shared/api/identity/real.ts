import { http, httpPage } from '../http'
import type { AccountDto, IdentityApi } from './types'

/** Страница GET /accounts — бэкенд отдаёт не больше 100 */
const ACCOUNTS_PAGE = 100

/** Identity API бэкенда: вход сотрудника, профиль, пользователи и роли */
export const identityApi: IdentityApi = {
  login: (login, password) => http('/auth/login', { method: 'POST', body: { login, password } }),
  demoAccounts: () => http('/auth/demo-accounts'),
  demoLogin: (login) => http('/auth/demo-login', { method: 'POST', body: { login } }),
  me: () => http('/me'),
  updateProfile: (data) => http('/me/profile', { method: 'PATCH', body: data }),
  listAccounts: (params = {}) => httpPage('/accounts', { query: { limit: params.limit ?? ACCOUNTS_PAGE, offset: params.offset } }),
  /** Все учётки страницами по 100: до total из X-Total-Count, без него — пока приходит полная страница */
  async listAllAccounts() {
    const all: AccountDto[] = []
    for (;;) {
      const page = await httpPage<AccountDto>('/accounts', { query: { limit: ACCOUNTS_PAGE, offset: all.length } })
      all.push(...page.items)
      const done = page.total !== null ? all.length >= page.total : page.items.length < ACCOUNTS_PAGE
      if (done || !page.items.length) return all
    }
  },
  createAccount: (data) => http('/accounts', { method: 'POST', body: data }),
  updateAccount: (id, data) => http(`/accounts/${id}`, { method: 'PATCH', body: data }),
  deleteAccount: (id) => http(`/accounts/${id}`, { method: 'DELETE' }),
  listRoles: () => http('/roles'),
  createRole: (data) => http('/roles', { method: 'POST', body: data }),
  updateRole: (id, data) => http(`/roles/${id}`, { method: 'PATCH', body: data }),
  deleteRole: (id) => http(`/roles/${id}`, { method: 'DELETE' }),
}
