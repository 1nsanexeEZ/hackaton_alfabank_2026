import { backofficeApi, type VersionStatus } from '@/shared/api'
import type { BadgeTone } from '@/shared/ui'

/** model — PD-модель (/scoring/models), policy — кредитная политика (/decision/policies) */
export type VersionKind = 'model' | 'policy'

export const VERSION_KINDS: readonly VersionKind[] = ['model', 'policy']

export const isVersionKind = (value: unknown): value is VersionKind => value === 'model' || value === 'policy'

export const VERSION_KIND_META: Record<VersionKind, { title: string; description: string }> = {
  model: {
    title: 'PD-модель',
    description: 'Сегменты, признаки, бины и баллы, калибровка и границы грейдов A–J',
  },
  policy: {
    title: 'Кредитная политика',
    description: 'Стоп-факторы, лимиты, ставка, маршрутизация, матрица двух моделей и требования закона',
  },
}

export const VERSION_STATUS_META: Record<VersionStatus, { label: string; tone: BadgeTone }> = {
  draft: { label: 'Черновик', tone: 'warning' },
  active: { label: 'Действует', tone: 'success' },
  archived: { label: 'В архиве', tone: 'neutral' },
}

/** Общие ручки версий; каталог и примерка у видов разные — их берут из backofficeApi напрямую */
export const versionsApi = (kind: VersionKind) =>
  kind === 'model' ? backofficeApi.scoringModels : backofficeApi.decisionPolicies
