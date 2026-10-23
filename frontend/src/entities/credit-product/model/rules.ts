import type { CreditProduct, RequiredDocument } from './types'

/** Те же правила, что у бэкенда при проверке комплектности (ProductTerms.needs_collateral / documents_for) */

export function needsCollateral(product: CreditProduct, amount: number): boolean {
  if (product.collateral === 'required') return true
  return product.collateralRequiredFrom !== null && amount >= product.collateralRequiredFrom
}

export function requiredDocumentsFor(product: CreditProduct, amount: number, legalForm: string): RequiredDocument[] {
  return product.requiredDocuments.filter(
    (document) =>
      (document.requiredFrom === null || amount >= document.requiredFrom) &&
      (document.legalForms.length === 0 || document.legalForms.includes(legalForm)),
  )
}

export function isAvailableFor(product: CreditProduct, legalForm: string): boolean {
  return product.legalForms.length === 0 || product.legalForms.includes(legalForm)
}

export function hasProductFields(product: CreditProduct): boolean {
  return Object.keys(product.fieldsSchema.properties ?? {}).length > 0
}

/** Шаг ползунка суммы: мелкий для небольших лимитов, крупный для больших */
export function amountStep(product: CreditProduct): number {
  return product.amount.max <= 10_000_000 ? 50_000 : 100_000
}

export function termStep(product: CreditProduct): number {
  return product.termMonths.max <= 12 ? 1 : 3
}
