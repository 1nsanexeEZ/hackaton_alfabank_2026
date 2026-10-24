/**
 * Контракт Identity API бэкенда (backend/src/identity/schemas.py).
 * Поля в snake_case, как их отдаёт бэкенд.
 */
import type { DemoAccountDto } from '../client/types'

export type Permission =
  | 'admin'
  | 'accounts.read'
  | 'accounts.create'
  | 'accounts.update'
  | 'accounts.delete'
  | 'roles.read'
  | 'roles.create'
  | 'roles.update'
  | 'roles.delete'
  | 'profile.update'
  /** Своё ФИО: у сотрудников; у клиента его нет — ФИО подтверждено банком */
  | 'profile.update_name'
  | 'requests.read'
  | 'requests.create'
  | 'requests.update'
  | 'requests.delete'
  | 'credits.read'
  | 'credits.create'
  | 'credits.update'
  | 'credits.delete'
  | 'organizations.read'
  | 'organizations.update'
  | 'tasks.read'
  | 'tasks.update'
  | 'decisions.read'
  | 'backoffice.read'
  | 'feed.read'
  | 'support.read'
  | 'support.create'
  | 'support.manage'

/** org_member — только компании, где пользователь участник, и их заявки */
export type Policy = 'not_deleted' | 'own_only' | 'org_member'

export type PolicyMap = Partial<Record<Permission, Policy[]>>

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
}

export interface RoleDto {
  id: string
  name: string
  description: string
  permissions: Permission[]
  policies: PolicyMap
  created_at: string
  updated_at: string
}

export interface RoleInput {
  name: string
  description: string
  permissions: Permission[]
  policies: PolicyMap
}

export interface ProfileDto {
  last_name: string
  first_name: string
  middle_name: string | null
  position: string | null
}

export interface AccountDto {
  id: string
  email: string | null
  phone: string | null
  role: { id: string; name: string }
  profile: ProfileDto | null
  created_at: string
  deleted_at: string | null
}

export interface MeDto extends AccountDto {
  permissions: Permission[]
  policies: PolicyMap
}

export interface AccountCreateInput {
  email?: string
  phone?: string
  password: string
  role_id: string
  profile: ProfileDto
}

export interface AccountUpdateInput {
  email?: string
  phone?: string
  password?: string
  role_id?: string
  profile?: Partial<ProfileDto>
}

/** Identity для рабочего места сотрудников; запросы подписываются токеном сотрудника */
export interface IdentityApi {
  login(login: string, password: string): Promise<TokenResponse>
  /** Демо-учётки стенда, и клиентов, и сотрудников; 404, если DEMO_LOGIN_ENABLED=false */
  demoAccounts(): Promise<DemoAccountDto[]>
  /** Вход в демо-учётку без пароля */
  demoLogin(login: string): Promise<TokenResponse>
  me(): Promise<MeDto>
  updateProfile(data: Partial<ProfileDto>): Promise<MeDto>
  listAccounts(params?: { limit?: number; offset?: number }): Promise<AccountDto[]>
  createAccount(data: AccountCreateInput): Promise<AccountDto>
  updateAccount(id: string, data: AccountUpdateInput): Promise<AccountDto>
  deleteAccount(id: string): Promise<void>
  listRoles(): Promise<RoleDto[]>
  createRole(data: RoleInput): Promise<RoleDto>
  updateRole(id: string, data: Partial<RoleInput>): Promise<RoleDto>
  deleteRole(id: string): Promise<void>
}
