import { reactive, ref, shallowRef, watch, type Ref } from 'vue'

import { founderPrescreen } from '@/entities/customer'
import { ApiError, clientApi, type BusinessPlanDto, type FinancialModelDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'

/** Горизонт финмодели по шаблону банка (project_v1.yaml) */
export const PLAN_MONTHS = 24

export type Guarantee = FinancialModelDto['guarantee']

/** Форма плана — строки, как в полях ввода; суммы в рублях, доля гарантии в процентах */
export interface BusinessPlanForm {
  summary: string
  loanAmount: string
  loanTermMonths: string
  ownFunds: string
  guarantee: Guarantee
  guaranteePercent: string
  collateralValue: string
  collateralDescription: string
  months: { revenue: string; expenses: string }[]
}

const toNumber = (value: string) => Number(value.replace(/\s/g, '').replace(',', '.'))
const text = (value: string | number) => String(Number(value))

function emptyForm(): BusinessPlanForm {
  return {
    summary: '',
    loanAmount: '',
    loanTermMonths: '36',
    ownFunds: '',
    guarantee: 'none',
    guaranteePercent: '50',
    collateralValue: '0',
    collateralDescription: '',
    months: Array.from({ length: PLAN_MONTHS }, () => ({ revenue: '', expenses: '' })),
  }
}

function formOf(plan: BusinessPlanDto): BusinessPlanForm {
  const model = plan.financial_model
  return {
    summary: plan.summary,
    loanAmount: text(model.loan_amount),
    loanTermMonths: String(model.loan_term_months),
    ownFunds: text(model.own_funds),
    guarantee: model.guarantee,
    guaranteePercent: model.guarantee === 'none' ? '50' : text(Number(model.guarantee_share) * 100),
    collateralValue: text(model.collateral_value),
    collateralDescription: model.collateral_description ?? '',
    months: Array.from({ length: PLAN_MONTHS }, (_, index) => ({
      revenue: model.months[index] ? text(model.months[index].revenue) : '',
      expenses: model.months[index] ? text(model.months[index].expenses) : '',
    })),
  }
}

/**
 * Бизнес-план и финмодель стартапа в кабинете компании (PUT/GET /organizations/{id}/business-plan),
 * до заявки: по ним банк делает проектную оценку. Заполняет участник с правом edit_financials.
 */
export function useBusinessPlan(organizationId: Ref<string>) {
  const plan = shallowRef<BusinessPlanDto | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const saving = ref(false)
  const form = reactive<BusinessPlanForm>(emptyForm())
  const errors = ref<Record<string, string>>({})

  watch(
    organizationId,
    async (id) => {
      plan.value = null
      error.value = null
      if (!id) return
      loading.value = true
      try {
        const loaded = await clientApi.businessPlan(id)
        if (id === organizationId.value) plan.value = loaded
      } catch (caught) {
        // 404 — план ещё не заполняли
        if (!(caught instanceof ApiError && caught.status === 404)) error.value = errorMessage(caught)
      } finally {
        loading.value = false
      }
    },
    { immediate: true },
  )

  /** Открыть форму: с текущим планом или пустую */
  function edit() {
    Object.assign(form, plan.value ? formOf(plan.value) : emptyForm())
    errors.value = {}
  }

  /** Заполнить все 24 месяца: выручка с первого месяца растёт на growth % в месяц, расходы постоянны */
  function fillMonths(firstRevenue: number, growthPercent: number, expenses: number) {
    form.months = Array.from({ length: PLAN_MONTHS }, (_, index) => ({
      revenue: String(Math.round(firstRevenue * (1 + growthPercent / 100) ** index)),
      expenses: String(Math.round(expenses)),
    }))
  }

  function validate(): boolean {
    const next: Record<string, string> = {}
    if (!form.summary.trim()) next.summary = 'Коротко опишите проект'
    if (!(toNumber(form.loanAmount) > 0)) next.loanAmount = 'Укажите сумму кредита'
    if (!(toNumber(form.loanTermMonths) > 0)) next.loanTermMonths = 'Укажите срок'
    if (!(toNumber(form.ownFunds) >= 0) || form.ownFunds.trim() === '') next.ownFunds = 'Укажите свои средства, хотя бы 0'
    if (!(toNumber(form.collateralValue) >= 0)) next.collateralValue = 'Стоимость обеспечения не может быть отрицательной'
    if (form.guarantee !== 'none') {
      const percent = toNumber(form.guaranteePercent)
      if (!(percent > 0 && percent <= 100)) next.guaranteePercent = 'Доля гарантии — от 1 до 100%'
    }
    const badMonth = form.months.findIndex(
      (month) => month.revenue.trim() === '' || month.expenses.trim() === '' || !(toNumber(month.revenue) >= 0) || !(toNumber(month.expenses) >= 0),
    )
    if (badMonth >= 0) next.months = `Заполните выручку и расходы за все ${PLAN_MONTHS} месяца — пропущен ${badMonth + 1}-й`
    errors.value = next
    return Object.keys(next).length === 0
  }

  /** Сохранить план: 201 — новый, 200 — уточнён, ревизия растёт */
  async function save(): Promise<boolean> {
    if (!validate()) return false
    saving.value = true
    error.value = null
    try {
      const saved = await clientApi.submitBusinessPlan(organizationId.value, {
        summary: form.summary.trim(),
        financial_model: {
          months: form.months.map((month) => ({ revenue: String(toNumber(month.revenue)), expenses: String(toNumber(month.expenses)) })),
          own_funds: String(toNumber(form.ownFunds)),
          collateral_value: String(toNumber(form.collateralValue)),
          collateral_description: form.collateralDescription.trim() || null,
          guarantee: form.guarantee,
          guarantee_share: form.guarantee === 'none' ? '0' : String(toNumber(form.guaranteePercent) / 100),
          loan_amount: String(toNumber(form.loanAmount)),
          loan_term_months: toNumber(form.loanTermMonths),
        },
      })
      plan.value = saved
      founderPrescreen.planSaved(organizationId.value, saved.revision)
      return true
    } catch (caught) {
      error.value = errorMessage(caught)
      return false
    } finally {
      saving.value = false
    }
  }

  return { plan, loading, error, saving, form, errors, edit, fillMonths, save }
}
