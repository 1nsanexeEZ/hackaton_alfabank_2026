import { API_MODE } from '../http'
import { mockIdentityApi } from './mock'
import { realIdentityApi } from './real'
import type { IdentityApi } from './types'

export const identityApi: IdentityApi = API_MODE === 'real' ? realIdentityApi : mockIdentityApi

export { MOCK_DEMO_ACCOUNTS } from './mock'
export type * from './types'
