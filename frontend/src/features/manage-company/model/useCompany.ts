import { computed, ref, shallowRef, watch } from 'vue'

import {
  clientApi,
  type FinancialReportDto,
  type FinancialReportInput,
  type MemberDto,
  type MemberRole,
  type OrganizationDetailDto,
  type OrganizationSummaryDto,
  type PowerOfAttorneyInput,
  type PreApprovedOfferDto,
  type VerificationResultDto,
} from '@/shared/api'
import { errorMessage } from '@/shared/lib'

/** Пересчёт предодобрения после нового отчёта идёт по событию — подождём и перечитаем */
const PRE_APPROVAL_RECALC_MS = 1_500

/**
 * Компания клиента: реквизиты из базы банка и сверка с ЕГРЮЛ, предодобрение, финотчётность,
 * участники и доверенности. Что можно менять — по правам внутри компании (my_permissions).
 */
export function useCompany() {
  const organizations = shallowRef<OrganizationSummaryDto[]>([])
  const organizationId = ref('')
  const detail = shallowRef<OrganizationDetailDto | null>(null)
  const reports = shallowRef<FinancialReportDto[]>([])
  const preApproved = shallowRef<PreApprovedOfferDto[]>([])
  const members = shallowRef<MemberDto[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const busy = ref<string | null>(null)
  const actionError = ref<string | null>(null)
  const notice = ref<string | null>(null)
  /** Итог последней ручной сверки с ЕГРЮЛ: что обновили молча */
  const verification = shallowRef<VerificationResultDto | null>(null)

  const can = (permission: string) => detail.value?.my_permissions.includes(permission as never) ?? false
  const canEditFinancials = computed(() => can('edit_financials'))
  const canManageMembers = computed(() => can('manage_members'))
  const canSubmit = computed(() => can('submit_application'))

  async function loadOrganizations() {
    loading.value = true
    error.value = null
    try {
      organizations.value = (await clientApi.listOrganizations()).filter((item) => item.my_role !== null)
      organizationId.value ||= organizations.value[0]?.id ?? ''
      if (organizationId.value) await loadCompany()
    } catch (caught) {
      error.value = errorMessage(caught)
    } finally {
      loading.value = false
    }
  }

  async function loadCompany() {
    const id = organizationId.value
    if (!id) return
    loading.value = true
    error.value = null
    try {
      const [nextDetail, nextReports, nextOffers, nextMembers] = await Promise.all([
        clientApi.getOrganization(id),
        clientApi.financialReports(id),
        clientApi.preApprovedOffers(id),
        clientApi.members(id),
      ])
      if (id !== organizationId.value) return
      detail.value = nextDetail
      reports.value = [...nextReports].sort((a, b) => b.period_year - a.period_year || (b.period_quarter ?? 0) - (a.period_quarter ?? 0))
      preApproved.value = nextOffers
      members.value = nextMembers
    } catch (caught) {
      error.value = errorMessage(caught)
    } finally {
      loading.value = false
    }
  }

  watch(organizationId, (next, previous) => {
    if (previous && next !== previous) {
      notice.value = null
      actionError.value = null
      verification.value = null
      void loadCompany()
    }
  })

  async function run(name: string, action: () => Promise<unknown>, success: string) {
    busy.value = name
    actionError.value = null
    notice.value = null
    try {
      await action()
      notice.value = success
      return true
    } catch (caught) {
      actionError.value = errorMessage(caught)
      return false
    } finally {
      busy.value = null
    }
  }

  const submitReport = (input: FinancialReportInput) =>
    run(
      'report',
      async () => {
        await clientApi.submitFinancialReport(organizationId.value, input)
        reports.value = await clientApi.financialReports(organizationId.value)
        // Новый отчёт пересчитывает предодобрение на бэкенде — показываем обновлённое
        setTimeout(async () => {
          try {
            preApproved.value = await clientApi.preApprovedOffers(organizationId.value)
          } catch {
            // Покажем при следующем открытии
          }
        }, PRE_APPROVAL_RECALC_MS)
      },
      'Отчёт отправлен. Предварительное одобрение пересчитается по новым данным.',
    )

  const addMember = (login: string, role: MemberRole) =>
    run(
      'member',
      async () => {
        await clientApi.addMember(organizationId.value, login.trim(), role)
        members.value = await clientApi.members(organizationId.value)
      },
      'Участник добавлен',
    )

  const grantPowerOfAttorney = (accountId: string, input: PowerOfAttorneyInput) =>
    run(
      `poa:${accountId}`,
      async () => {
        await clientApi.grantPowerOfAttorney(organizationId.value, accountId, input)
        members.value = await clientApi.members(organizationId.value)
      },
      'Доверенность выдана',
    )

  /** Сверка с ЕГРЮЛ/ЕГРИП мимо кэша: адрес, КПП, ОКВЭД, наименование обновляются, руководитель — в расхождения */
  const verify = () =>
    run(
      'verify',
      async () => {
        const result = await clientApi.verifyOrganization(organizationId.value)
        detail.value = result.organization
        verification.value = result
      },
      'Реквизиты обновлены',
    )

  const changeMemberRole = (accountId: string, role: MemberRole) =>
    run(
      `role:${accountId}`,
      async () => {
        await clientApi.changeMemberRole(organizationId.value, accountId, role)
        members.value = await clientApi.members(organizationId.value)
      },
      'Роль изменена',
    )

  const removeMember = (accountId: string) =>
    run(
      `remove:${accountId}`,
      async () => {
        await clientApi.removeMember(organizationId.value, accountId)
        members.value = await clientApi.members(organizationId.value)
      },
      'Участник удалён из компании',
    )

  return {
    organizations,
    organizationId,
    detail,
    reports,
    preApproved,
    members,
    loading,
    error,
    busy,
    actionError,
    notice,
    verification,
    canEditFinancials,
    canSubmit,
    canManageMembers,
    loadOrganizations,
    loadCompany,
    submitReport,
    addMember,
    grantPowerOfAttorney,
    verify,
    changeMemberRole,
    removeMember,
  }
}

export type CompanyModel = ReturnType<typeof useCompany>
