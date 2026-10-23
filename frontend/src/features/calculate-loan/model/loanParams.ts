import type { ApplicationDraft } from '@/entities/application'
import type { CreditProduct } from '@/entities/credit-product'
import { clamp } from '@/shared/lib'

const DEFAULT_AMOUNT = 3_000_000
const DEFAULT_TERM_MONTHS = 24

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
