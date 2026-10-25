import { computed, ref, shallowRef, toValue, watch, type MaybeRefOrGetter } from 'vue'

import { PRODUCT_KIND_LABEL, PURPOSE_LABEL, type CreditProduct, type ProductKind } from '@/entities/credit-product'
import { clientApi, type LoanPurpose } from '@/shared/api'

export type ProductFilter = 'all' | ProductKind

export const PRODUCT_FILTER_OPTIONS: readonly { value: ProductFilter; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'lump-sum', label: PRODUCT_KIND_LABEL['lump-sum'] },
  { value: 'revolving', label: PRODUCT_KIND_LABEL.revolving },
]

/** Пусто — любая цель */
export type PurposeFilter = '' | LoanPurpose

export const PURPOSE_FILTER_OPTIONS: readonly { value: PurposeFilter; label: string }[] = [
  { value: '', label: 'Любая цель' },
  ...(Object.entries(PURPOSE_LABEL) as [LoanPurpose, string][]).map(([value, label]) => ({ value, label })),
]

/**
 * Витрина: вид продукта фильтруем на месте, цель кредита — на бэкенде (GET /products?purpose=):
 * он знает, какие продукты под какую цель. Пока коды не пришли — показываем каталог как есть.
 */
export function useProductFilter(products: MaybeRefOrGetter<readonly CreditProduct[]>) {
  const filter = ref<ProductFilter>('all')
  const purpose = ref<PurposeFilter>('')
  const purposeCodes = shallowRef<Set<string> | null>(null)
  const purposeError = ref(false)

  let requestId = 0
  watch(purpose, async (value) => {
    const current = ++requestId
    purposeError.value = false
    if (!value) {
      purposeCodes.value = null
      return
    }
    try {
      const list = await clientApi.listProducts(value)
      if (current === requestId) purposeCodes.value = new Set(list.map((product) => product.code))
    } catch {
      // Фильтр не сработал — показываем весь каталог, а не пустую витрину
      if (current === requestId) {
        purposeCodes.value = null
        purposeError.value = true
      }
    }
  })

  const filteredProducts = computed(() =>
    toValue(products).filter(
      (product) =>
        (filter.value === 'all' || product.kind === filter.value) && (!purposeCodes.value || purposeCodes.value.has(product.code)),
    ),
  )

  return { filter, purpose, purposeError, filteredProducts }
}
