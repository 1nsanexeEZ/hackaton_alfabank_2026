import type { CreditProduct, ProductCatalog } from './types'

/** Продукт каталога по id карточки; не нашёлся — первый в каталоге */
export function findProduct(catalog: ProductCatalog, id: string): CreditProduct {
  return catalog.find((product) => product.id === id) ?? catalog[0]
}
