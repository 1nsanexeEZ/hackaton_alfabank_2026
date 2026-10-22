import { computed, reactive } from 'vue'

import { clientApi } from '@/shared/api'
import { errorMessage } from '@/shared/lib'

import { toCreditProduct } from './mapper'
import type { ProductCatalog } from './types'

/**
 * Каталог продуктов из GET /products. Загружается один раз на всё приложение:
 * его читают витрина, калькулятор, hero, подвал и форма заявки.
 */
const state = reactive<{ products: ProductCatalog | null; loading: boolean; error: string | null }>({
  products: null,
  loading: false,
  error: null,
})

let pending: Promise<void> | null = null

function load(): Promise<void> {
  pending ??= (async () => {
    state.loading = true
    state.error = null
    try {
      const products = (await clientApi.listProducts())
        .filter((product) => product.status === 'active')
        .map(toCreditProduct)
      const [first, ...rest] = products
      if (!first) throw new Error('Каталог продуктов пуст')
      state.products = [first, ...rest]
    } catch (error) {
      state.error = errorMessage(error)
    } finally {
      state.loading = false
      pending = null
    }
  })()
  return pending
}

export function useProductCatalog() {
  if (!state.products && !state.error) void load()
  return {
    products: computed(() => state.products),
    loading: computed(() => !state.products && !state.error),
    error: computed(() => state.error),
    reload: load,
  }
}
