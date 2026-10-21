import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { PRODUCT_KIND_LABEL, type CreditProduct, type ProductKind } from '@/entities/credit-product'

export type ProductFilter = 'all' | ProductKind

export const PRODUCT_FILTER_OPTIONS: readonly { value: ProductFilter; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'lump-sum', label: PRODUCT_KIND_LABEL['lump-sum'] },
  { value: 'revolving', label: PRODUCT_KIND_LABEL.revolving },
]

export function useProductFilter(products: MaybeRefOrGetter<readonly CreditProduct[]>) {
  const filter = ref<ProductFilter>('all')

  const filteredProducts = computed(() => {
    const list = toValue(products)
    return filter.value === 'all' ? list : list.filter((product) => product.kind === filter.value)
  })

  return { filter, filteredProducts }
}
