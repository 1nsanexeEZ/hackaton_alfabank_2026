import type { ApplicationDraft } from '@/entities/application'
import type { CreditProduct } from '@/entities/credit-product'
import { clamp } from '@/shared/lib'

const DEFAULT_AMOUNT = 3_000_000
const DEFAULT_TERM_MONTHS = 24

/** Шаг ползунка суммы: мелкий для небольших лимитов, крупный для больших */
export function getAmountStep(product: CreditProduct): number {
  return product.amount.max <= 10_000_000 ? 50_000 : 100_000
}

export function getTermStep(product: CreditProduct): number {
  return product.termMonths.max <= 12 ? 1 : 3
}

/** Приводит сумму и срок к лимитам продукта */
export function fitLoanParams(product: CreditProduct, amount: number, termMonths: number) {
  return {
    amount: clamp(amount, product.amount.min, product.amount.max),
    termMonths: clamp(termMonths, product.termMonths.min, product.termMonths.max),
  }
}

export function getDefaultLoanParams(product: CreditProduct): ApplicationDraft {
  return { productId: product.id, ...fitLoanParams(product, DEFAULT_AMOUNT, DEFAULT_TERM_MONTHS) }
}
