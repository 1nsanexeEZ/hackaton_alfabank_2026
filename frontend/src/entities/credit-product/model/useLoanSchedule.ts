import { onScopeDispose, ref, shallowRef, toValue, watch, type MaybeRefOrGetter } from 'vue'

import { clientApi, type Repayment } from '@/shared/api'
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

/**
 * График платежей из POST /products/{code}/calculate. Пока ответа нет, показываем локальную
 * аннуитетную оценку, чтобы цифры не «прыгали» в пустоту; если бэкенд недоступен — она и остаётся.
 */
export function useLoanSchedule(params: MaybeRefOrGetter<LoanParams | null>) {
  const schedule = shallowRef<LoanSchedule | null>(null)
  const pending = ref(false)
  /** true — цифры посчитаны в браузере, а не бэкендом */
  const estimated = ref(true)

  let timer: ReturnType<typeof setTimeout> | undefined
  let requestId = 0

  async function request(current: LoanParams, id: number) {
    try {
      const result = await clientApi.calculate(current.product.code, {
        amount: current.amount,
        term_months: current.termMonths,
      })
      if (id !== requestId) return
      schedule.value = {
        monthlyPayment: Number(result.monthly_payment),
        totalInterest: Number(result.total_interest),
        totalPaid: Number(result.total_paid),
        rate: Number(result.rate),
        repayment: result.repayment,
      }
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
    (current) => {
      clearTimeout(timer)
      const id = ++requestId
      if (!current) {
        schedule.value = null
        pending.value = false
        return
      }
      if (!schedule.value) schedule.value = estimate(current)
      pending.value = true
      timer = setTimeout(() => void request(current, id), DEBOUNCE_MS)
    },
    { immediate: true, deep: true },
  )

  onScopeDispose(() => clearTimeout(timer))

  return { schedule, pending, estimated }
}
