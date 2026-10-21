/**
 * Контракт Identity API бэкенда (backend/src/identity/schemas.py).
 * Поля в snake_case, как их отдаёт бэкенд.
 */
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
  | 'requests.read'
  | 'requests.create'
  | 'requests.update'
  | 'requests.delete'
  | 'credits.read'
  | 'credits.create'
  | 'credits.update'
  | 'credits.delete'

export type Policy = 'not_deleted' | 'own_only'

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

export interface IdentityApi {
  login(login: string, password: string): Promise<TokenResponse>
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
