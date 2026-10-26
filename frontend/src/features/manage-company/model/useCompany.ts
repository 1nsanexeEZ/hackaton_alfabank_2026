import { computed, ref, shallowRef, watch } from 'vue'

import {
  ApiError,
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

/** Номер доверенности — как проверяет бэкенд: буквы и цифры, между ними пробел, точка, / или -, хотя бы одна цифра */
export const POA_NUMBER_HINT = 'Номер: буквы и цифры, можно пробел, точку, / и -, хотя бы одна цифра, до 32 знаков'
const POA_NUMBER = /^[0-9A-Za-zА-Яа-яЁё]+(?:[ ./-]+[0-9A-Za-zА-Яа-яЁё]+)*$/

/** Знак № в начале и лишние пробелы бэкенд убирает сам — так же и мы перед проверкой */
export const normalizePoaNumber = (value: string) => value.replace(/^\s*№\s*/, '').replace(/\s+/g, ' ').trim()

export function poaNumberError(value: string): string | null {
  const number = normalizePoaNumber(value)
  if (!number) return 'Укажите номер доверенности'
  return number.length <= 32 && POA_NUMBER.test(number) && /\d/.test(number) ? null : POA_NUMBER_HINT
}

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
  /** Ошибка формы доверенности: про номер — под полем номера, остальное — над кнопками формы */
  const poaError = shallowRef<{ field: 'number' | null; message: string } | null>(null)
  /** Ошибка добавления участника — под полем «Email или телефон» */
  const memberError = ref<string | null>(null)

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

  async function addMember(login: string, role: MemberRole) {
    busy.value = 'member'
    actionError.value = null
    notice.value = null
    memberError.value = null
    try {
      await clientApi.addMember(organizationId.value, login.trim(), role)
      members.value = await clientApi.members(organizationId.value)
      notice.value = 'Участник добавлен'
      return true
    } catch (caught) {
      // Добавить можно только того, у кого уже есть учётная запись в банке: сначала его подключает банк
      memberError.value =
        caught instanceof ApiError && caught.details.code === 'account_not_found'
          ? 'Такого клиента в банке нет. Добавить можно сотрудника, у которого уже есть вход в кабинет — по его email или телефону'
          : errorMessage(caught)
      return false
    } finally {
      busy.value = null
    }
  }

  async function grantPowerOfAttorney(accountId: string, input: PowerOfAttorneyInput) {
    busy.value = `poa:${accountId}`
    actionError.value = null
    notice.value = null
    poaError.value = null
    try {
      await clientApi.grantPowerOfAttorney(organizationId.value, accountId, input)
      members.value = await clientApi.members(organizationId.value)
      notice.value = 'Доверенность выдана'
      return true
    } catch (caught) {
      const code = caught instanceof ApiError ? caught.details.code : undefined
      const message = code === 'invalid_format' ? POA_NUMBER_HINT : errorMessage(caught)
      poaError.value = { field: code === 'invalid_format' || code === 'number_taken' ? 'number' : null, message }
      return false
    } finally {
      busy.value = null
    }
  }

  /** Отзыв: права участника меняются сразу — перечитываем участников и предодобрение (без права подачи его не видно) */
  const revokePowerOfAttorney = (accountId: string) =>
    run(
      `revoke:${accountId}`,
      async () => {
        await clientApi.revokePowerOfAttorney(organizationId.value, accountId)
        const [nextMembers, nextOffers] = await Promise.all([
          clientApi.members(organizationId.value),
          clientApi.preApprovedOffers(organizationId.value),
        ])
        members.value = nextMembers
        preApproved.value = nextOffers
      },
      'Доверенность отозвана',
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
    poaError,
    memberError,
    canEditFinancials,
    canSubmit,
    canManageMembers,
    loadOrganizations,
    loadCompany,
    submitReport,
    addMember,
    grantPowerOfAttorney,
    revokePowerOfAttorney,
    verify,
    changeMemberRole,
    removeMember,
  }
}

export type CompanyModel = ReturnType<typeof useCompany>
