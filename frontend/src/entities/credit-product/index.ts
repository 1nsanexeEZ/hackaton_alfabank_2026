export { DEMO_CREDIT_PRODUCTS, findProduct } from './model/catalog'
export { toCreditProduct } from './model/mapper'
export {
  amountStep,
  hasProductFields,
  isAvailableFor,
  needsCollateral,
  requiredDocumentsFor,
  termStep,
} from './model/rules'
export {
  COLLATERAL_LABEL,
  COLLATERAL_TYPE_LABEL,
  PRODUCT_KIND_LABEL,
  PURPOSE_LABEL,
  REPAYMENT_LABEL,
  type Collateral,
  type CreditProduct,
  type NumberRange,
  type ProductCatalog,
  type ProductKind,
  type RequiredDocument,
} from './model/types'
export { useLoanSchedule, type LoanParams, type LoanSchedule } from './model/useLoanSchedule'
export { useProductCatalog } from './model/useProductCatalog'
export { default as ProductCard } from './ui/ProductCard.vue'
export { default as ProductFlexCard } from './ui/ProductFlexCard.vue'
