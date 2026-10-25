import { http } from '../http'
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
  listAccounts: (params = {}) => http('/accounts', { query: { limit: params.limit ?? ACCOUNTS_PAGE, offset: params.offset } }),
  async listAllAccounts() {
    const all: AccountDto[] = []
    for (;;) {
      const page = await http<AccountDto[]>('/accounts', { query: { limit: ACCOUNTS_PAGE, offset: all.length } })
      all.push(...page)
      if (page.length < ACCOUNTS_PAGE) return all
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
