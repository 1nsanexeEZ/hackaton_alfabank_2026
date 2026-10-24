import { onScopeDispose, ref, shallowRef, toValue, watch, type MaybeRefOrGetter } from 'vue'

import { clientApi, type EligibilityReasonDto, type PaymentScheduleDto, type PersonalScheduleDto, type Repayment } from '@/shared/api'
import { calcLoanSummary } from '@/shared/lib'

import type { CreditProduct } from './types'

export interface LoanSchedule {
  monthlyPayment: number
  totalInterest: number
  totalPaid: number
  /** Годовая ставка, по которой посчитан график, % */
  rate: number
  repayment: Repayment
}

export interface LoanParams {
  product: CreditProduct
  amount: number
  termMonths: number
  /** Компания вошедшего клиента: график по ставке её предодобрения, с причинами и подсказкой */
  organizationId?: string | null
}

/** Что калькулятор знает о компании сверх графика (POST /bff/products/{code}/calculate) */
export interface PersonalTerms {
  preApproved: { maxAmount: number; rateFrom: number; termMaxMonths: number; validUntil: string } | null
  /** null — по продукту ничего не предодобрено */
  withinPreApproved: boolean | null
  eligible: boolean
  /** Невыполненные условия: eligibility, сумма или срок сверх предодобренного или посильного */
  problems: EligibilityReasonDto[]
  /** Запрос, урезанный до посильного */
  suggestion: { amount: number; termMonths: number; monthlyPayment: number } | null
  /** До какой суммы банк готов предложить на выбранный срок; null — предодобрения нет */
  maxAffordable: number | null
  /** Что ограничило: предодобрение, платёжеспособность по отчётности (40% свободного потока), проектная оценка стартапа */
  affordableBy: 'pre_approved' | 'payment' | 'project' | null
  /** Запрос больше посильного: заявку примут, решит специалист */
  aboveAffordable: boolean
}

const DEBOUNCE_MS = 250

function estimate({ product, amount, termMonths }: LoanParams): LoanSchedule {
  const summary = calcLoanSummary(amount, product.rateFrom, termMonths)
  return {
    monthlyPayment: summary.monthlyPayment,
    totalInterest: summary.overpayment,
    totalPaid: summary.totalPayment,
    rate: product.rateFrom,
    repayment: 'annuity',
  }
}

function toSchedule(result: PaymentScheduleDto): LoanSchedule {
  return {
    monthlyPayment: Number(result.monthly_payment),
    totalInterest: Number(result.total_interest),
    totalPaid: Number(result.total_paid),
    rate: Number(result.rate),
    repayment: result.repayment,
  }
}

function toPersonal(result: PersonalScheduleDto): PersonalTerms {
  const pre = result.pre_approved
  return {
    preApproved: pre
      ? { maxAmount: Number(pre.max_amount), rateFrom: Number(pre.rate_from), termMaxMonths: pre.term_max_months, validUntil: pre.valid_until }
      : null,
    withinPreApproved: result.within_pre_approved,
    eligible: result.eligible,
    problems: result.reasons.filter((reason) => !reason.passed),
    suggestion: result.suggestion
      ? {
          amount: Number(result.suggestion.amount),
          termMonths: result.suggestion.term_months,
          monthlyPayment: Number(result.suggestion.monthly_payment),
        }
      : null,
    maxAffordable: result.max_affordable ? Number(result.max_affordable) : null,
    affordableBy: result.affordable_by ?? null,
    aboveAffordable: result.above_affordable ?? false,
  }
}

/**
 * График платежей. С компанией — POST /bff/products/{code}/calculate: ставка предодобрения, причины и
 * подсказка; без неё — POST /products/{code}/calculate по базовой ставке. Пока ответа нет, показываем
 * локальную аннуитетную оценку, чтобы цифры не «прыгали» в пустоту; если бэкенд недоступен — она и остаётся.
 */
export function useLoanSchedule(params: MaybeRefOrGetter<LoanParams | null>) {
  const schedule = shallowRef<LoanSchedule | null>(null)
  const personal = shallowRef<PersonalTerms | null>(null)
  const pending = ref(false)
  /** true — цифры посчитаны в браузере, а не бэкендом */
  const estimated = ref(true)

  let timer: ReturnType<typeof setTimeout> | undefined
  let requestId = 0

  async function request(current: LoanParams, id: number) {
    const input = { amount: current.amount, term_months: current.termMonths }
    try {
      if (current.organizationId) {
        try {
          const result = await clientApi.calculateFor(current.product.code, current.organizationId, input)
          if (id !== requestId) return
          schedule.value = toSchedule(result.schedule)
          personal.value = toPersonal(result)
          estimated.value = false
          return
        } catch {
          // Персональный расчёт не удался — считаем как для гостя, по базовой ставке
          if (id !== requestId) return
          personal.value = null
        }
      }
      const result = await clientApi.calculate(current.product.code, input)
      if (id !== requestId) return
      schedule.value = toSchedule(result)
      estimated.value = false
    } catch {
      if (id !== requestId) return
      schedule.value = estimate(current)
      estimated.value = true
    } finally {
      if (id === requestId) pending.value = false
    }
  }

  watch(
    () => {
      const current = toValue(params)
      return current && { ...current }
    },
    (current, previous) => {
      clearTimeout(timer)
      const id = ++requestId
      if (!current) {
        schedule.value = null
        personal.value = null
        pending.value = false
        return
      }
      // Сменилась компания или продукт — прежние причины и предодобрение уже не про них
      if (current.organizationId !== previous?.organizationId || current.product.code !== previous?.product.code) {
        personal.value = null
      }
      if (!schedule.value) schedule.value = estimate(current)
      pending.value = true
      timer = setTimeout(() => void request(current, id), DEBOUNCE_MS)
    },
    { immediate: true, deep: true },
  )

  onScopeDispose(() => clearTimeout(timer))

  return { schedule, personal, pending, estimated }
}
