import { onScopeDispose, ref, shallowRef, toValue, watch, type MaybeRefOrGetter } from 'vue'

import { clientApi, type LoanPurpose } from '@/shared/api'
import { errorMessage } from '@/shared/lib'

export interface RecommendationNeed {
  purpose: LoanPurpose
  amount: number
  termMonths: number
  /** Компания вошедшего клиента: тогда бэкенд проверит её и подставит предодобрение */
  organizationId?: string | null
}

export interface ProductRecommendation {
  code: string
  rank: number
  /** available — подходит; needs_adjustment — подойдёт, если поменять сумму или срок; unavailable — нет */
  status: 'available' | 'needs_adjustment' | 'unavailable'
  /** Сумма и срок, подогнанные под рамки продукта — с ними и открываем заявку */
  amount: number
  termMonths: number
  paymentFrom: number
  paymentTo: number
  /** Что поменять, чтобы продукт подошёл */
  adjustments: string[]
  /** Подходит ли компания (форма, возраст, выручка); null — клиент не вошёл */
  eligible: boolean | null
  /** Почему компания не подходит */
  notEligibleReasons: string[]
  /** Предварительно одобренный максимум по продукту для компании */
  preApprovedMax: number | null
}

const DEBOUNCE_MS = 350

/**
 * Подбор продукта под задачу: `POST /products/recommend` — продукты под цель, платёж, что поменять;
 * для вошедшего ещё `GET /bff/products/recommend` — подходит ли его компания и сколько ей предодобрено.
 */
export function useRecommendations(need: MaybeRefOrGetter<RecommendationNeed | null>) {
  const items = shallowRef<ProductRecommendation[] | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const cashGapExpected = ref<boolean | null>(null)

  let timer: ReturnType<typeof setTimeout> | undefined
  let requestId = 0

  async function load(current: RecommendationNeed, id: number) {
    const body = { purpose: current.purpose, amount: current.amount, term_months: current.termMonths }
    try {
      const [open, personal] = await Promise.all([
        clientApi.recommend(body),
        current.organizationId ? clientApi.recommendFor(body, current.organizationId).catch(() => null) : null,
      ])
      if (id !== requestId) return
      const byCode = new Map((personal?.items ?? []).map((item) => [item.product_code, item]))
      cashGapExpected.value = open.cash_gap_expected ?? null
      items.value = open.items.map((item) => {
        const own = byCode.get(item.product.code)
        return {
          code: item.product.code,
          rank: item.rank,
          status: item.status,
          amount: Number(item.amount),
          termMonths: item.term_months,
          paymentFrom: Number(item.monthly_payment_from),
          paymentTo: Number(item.monthly_payment_to),
          adjustments: item.adjustments,
          eligible: own ? own.eligible : null,
          notEligibleReasons: own ? own.eligibility.filter((reason) => !reason.passed).map((reason) => reason.message) : [],
          preApprovedMax: own?.pre_approved_max ? Number(own.pre_approved_max) : null,
        }
      })
      error.value = null
    } catch (caught) {
      if (id === requestId) error.value = errorMessage(caught)
    } finally {
      if (id === requestId) loading.value = false
    }
  }

  watch(
    () => {
      const current = toValue(need)
      return current && { ...current }
    },
    (current) => {
      clearTimeout(timer)
      const id = ++requestId
      if (!current) {
        items.value = null
        loading.value = false
        return
      }
      loading.value = true
      timer = setTimeout(() => void load(current, id), DEBOUNCE_MS)
    },
    { immediate: true, deep: true },
  )

  onScopeDispose(() => clearTimeout(timer))

  return { items, loading, error, cashGapExpected }
}
