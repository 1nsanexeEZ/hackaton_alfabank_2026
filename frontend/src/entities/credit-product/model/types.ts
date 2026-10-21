/** Как клиент получает деньги: всей суммой сразу или частями в пределах лимита */
export type ProductKind = 'lump-sum' | 'revolving'

export type Collateral = 'none' | 'required' | 'optional'

export interface NumberRange {
  min: number
  max: number
}

export interface CreditProduct {
  id: string
  kind: ProductKind
  title: string
  description: string
  /** Годовая ставка, % */
  rateFrom: number
  /** Сумма, ₽ */
  amount: NumberRange
  termMonths: NumberRange
  collateral: Collateral
  /** Типичное время решения, например «5 минут» */
  decisionTime: string
  /** 2–3 слова, которые продают продукт с первого взгляда — для компактной витрины */
  keywords: readonly string[]
  tag?: string
}

/** Каталог никогда не пустой: калькулятору и форме всегда есть что выбрать по умолчанию */
export type ProductCatalog = readonly [CreditProduct, ...CreditProduct[]]

export const PRODUCT_KIND_LABEL: Record<ProductKind, string> = {
  'lump-sum': 'Одной суммой',
  revolving: 'Деньги частями',
}

export const COLLATERAL_LABEL: Record<Collateral, string> = {
  none: 'Без залога',
  required: 'С залогом',
  optional: 'Залог по желанию',
}
