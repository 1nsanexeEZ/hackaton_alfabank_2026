import { reactive, readonly, watch } from 'vue'

import {
  clientApi,
  type CompanySegment,
  type EligibilityReasonDto,
  type FounderPrescreenDto,
  type FounderPrescreenSummaryDto,
  type ProjectAssessmentDto,
} from '@/shared/api'

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
  /** Ревизия бизнес-плана; null — план ещё не заполнен */
  businessPlanRevision: number | null
  /** Последняя проектная оценка банка; null — ещё не оценивали */
  project: ProjectAssessmentDto | null
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
          businessPlanRevision: dashboard.startup?.business_plan_revision ?? null,
          project: dashboard.startup?.project ?? null,
        }
        byOrganization[organizationId] = info
        return info
      })
      .catch(() => {
        // Не узнали сегмент — считаем компанию действующей: продукт для стартапа бэкенд всё равно проверит сам
        const info: CompanyStartupInfo = { segment: 'established', prescreen: null, businessPlanRevision: null, project: null }
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
  byOrganization[organizationId] = { ...known(organizationId), prescreen: result }
  return result
}

const known = (organizationId: string): CompanyStartupInfo =>
  byOrganization[organizationId] ?? { segment: 'startup', prescreen: null, businessPlanRevision: null, project: null }

/**
 * Проектная оценка по текущему бизнес-плану (POST /organizations/{id}/project-assessment): пройдена —
 * «вам предодобрен кредит до max_amount», то же предложение появляется в предодобренных (basis = project)
 */
async function runProject(organizationId: string): Promise<ProjectAssessmentDto> {
  const result = await clientApi.runProjectAssessment(organizationId)
  byOrganization[organizationId] = { ...known(organizationId), project: result }
  return result
}

/** План сохранили — запоминаем ревизию: оценка по старой ревизии устарела */
function planSaved(organizationId: string, revision: number): void {
  byOrganization[organizationId] = { ...known(organizationId), businessPlanRevision: revision }
}

/** Что нужно знать о проекте, чтобы сказать «оценка действует» — подходит и readonly-состояние стора */
interface ProjectState {
  project: Pick<ProjectAssessmentDto, 'status' | 'valid' | 'plan_revision'> | null
  businessPlanRevision: number | null
}

/** Оценка по прежней редакции плана: план уточнили после неё — стоит оценить заново */
export const projectOutdated = (info: ProjectState | null | undefined) =>
  Boolean(info?.project && info.businessPlanRevision !== null && info.project.plan_revision < info.businessPlanRevision)

/** Проект оценён, оценка пройдена, действует и сделана по текущему плану */
export const projectApproved = (info: ProjectState | null | undefined) =>
  Boolean(info?.project && info.project.status === 'passed' && info.project.valid && !projectOutdated(info))

/** Можно ли подавать заявку на продукт для стартапа: предскрининг пройден и не истёк */
export const prescreenPassed = (prescreen: Pick<FounderPrescreen, 'status' | 'valid'> | null | undefined) =>
  Boolean(prescreen && prescreen.status === 'passed' && prescreen.valid)

export const founderPrescreen = {
  state: readonly(byOrganization),
  load,
  run,
  runProject,
  planSaved,
}
