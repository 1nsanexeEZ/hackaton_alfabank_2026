import { reactive, readonly, watch } from 'vue'

import { clientApi, type CompanySegment, type EligibilityReasonDto, type FounderPrescreenDto, type FounderPrescreenSummaryDto } from '@/shared/api'

import { customer } from './session'

/** Итог предскрининга учредителя — одинаково из дашборда и из ответа на запуск проверки */
export interface FounderPrescreen {
  status: 'passed' | 'failed'
  founderName: string
  checkedAt: string
  validUntil: string
  /** Пройден и ещё не истёк — с ним можно подавать заявку на продукт для стартапа */
  valid: boolean
  reasons: EligibilityReasonDto[]
}

export interface CompanyStartupInfo {
  /** startup — бизнес младше 6 месяцев или без годового отчёта: ему — только продукты для стартапа */
  segment: CompanySegment
  /** Последний предскрининг учредителя; null — ещё не проходили (или компания не стартап) */
  prescreen: FounderPrescreen | null
}

function fromSummary(item: FounderPrescreenSummaryDto): FounderPrescreen {
  return {
    status: item.status,
    founderName: item.founder_name,
    checkedAt: item.checked_at,
    validUntil: item.valid_until,
    valid: item.valid,
    reasons: item.reasons,
  }
}

function fromRun(item: FounderPrescreenDto): FounderPrescreen {
  return {
    status: item.status,
    founderName: item.founder.name,
    checkedAt: item.checked_at,
    validUntil: item.valid_until,
    valid: item.valid,
    reasons: item.reasons,
  }
}

/**
 * Ветка стартапа (docs/api/client-journey.md §4.6): сегмент компании и предскрининг учредителя по его личной
 * кредитной истории. Берём из GET /bff/dashboard?organization_id= — там и сегмент, и последний предскрининг.
 */
const byOrganization = reactive<Record<string, CompanyStartupInfo>>({})
const loading = new Map<string, Promise<CompanyStartupInfo>>()

watch(
  () => customer.state.me?.id ?? null,
  () => {
    for (const key of Object.keys(byOrganization)) delete byOrganization[key]
    loading.clear()
  },
)

function load(organizationId: string, force = false): Promise<CompanyStartupInfo> {
  const known = byOrganization[organizationId]
  if (known && !force) return Promise.resolve(known)
  let pending = force ? undefined : loading.get(organizationId)
  if (!pending) {
    pending = clientApi
      .dashboard(organizationId)
      .then((dashboard) => {
        const info: CompanyStartupInfo = {
          segment: dashboard.organization?.segment ?? 'established',
          prescreen: dashboard.startup?.prescreen ? fromSummary(dashboard.startup.prescreen) : null,
        }
        byOrganization[organizationId] = info
        return info
      })
      .catch(() => {
        // Не узнали сегмент — считаем компанию действующей: продукт для стартапа бэкенд всё равно проверит сам
        const info: CompanyStartupInfo = { segment: 'established', prescreen: null }
        return info
      })
      .finally(() => loading.delete(organizationId))
    loading.set(organizationId, pending)
  }
  return pending
}

/** Запустить предскрининг: 422 consent_required — у учредителя нет согласия на свою кредитную историю */
async function run(organizationId: string): Promise<FounderPrescreen> {
  const result = fromRun(await clientApi.runFounderPrescreen(organizationId))
  byOrganization[organizationId] = { segment: byOrganization[organizationId]?.segment ?? 'startup', prescreen: result }
  return result
}

/** Можно ли подавать заявку на продукт для стартапа: предскрининг пройден и не истёк */
export const prescreenPassed = (prescreen: Pick<FounderPrescreen, 'status' | 'valid'> | null | undefined) =>
  Boolean(prescreen && prescreen.status === 'passed' && prescreen.valid)

export const founderPrescreen = {
  state: readonly(byOrganization),
  load,
  run,
}
