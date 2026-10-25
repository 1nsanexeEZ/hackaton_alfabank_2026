import type { ProductDto } from '@/shared/api'

import type { Collateral, CreditProduct, ProductKind } from './types'

/**
 * Витринный текст, которого нет в API: короткие слова для карточки, метка и привычное время решения.
 * Неизвестный продукт тоже покажется — с нейтральными значениями.
 */
const PRESENTATION: Record<string, Pick<CreditProduct, 'keywords' | 'decisionTime' | 'tag'>> = {
  unsecured: { keywords: ['Без залога', 'Быстро', 'На любые цели'], decisionTime: '5 минут', tag: 'Популярный' },
  secured: { keywords: ['Крупная сумма', 'Надолго', 'Ставка ниже'], decisionTime: '1 рабочий день' },
  'credit-line': { keywords: ['Частями', 'Свой лимит', 'Гибко'], decisionTime: '1 рабочий день' },
  overdraft: { keywords: ['Кассовый разрыв', 'Сразу', 'Подушка'], decisionTime: '5 минут' },
  auto: { keywords: ['Транспорт', 'Залог — покупка', 'До 7 лет'], decisionTime: '1 рабочий день' },
  mortgage: { keywords: ['Недвижимость', 'До 10 лет', 'Для ООО и АО'], decisionTime: '3 рабочих дня' },
  refinance: { keywords: ['Один платёж', 'Ставка ниже', 'Один график'], decisionTime: '1 рабочий день' },
  'gov-support': { keywords: ['Льготная ставка', 'Господдержка', 'МСП'], decisionTime: '1 рабочий день' },
  startup: { keywords: ['Новый бизнес', 'Без оборотов', 'Господдержка'], decisionTime: '3 рабочих дня', tag: 'До 6 месяцев' },
}

const KIND_BY_FACILITY: Record<ProductDto['facility'], ProductKind> = {
  term_loan: 'lump-sum',
  credit_line_revolving: 'revolving',
  credit_line_non_revolving: 'revolving',
  overdraft: 'revolving',
}

const toNumber = (value: string | null) => (value === null ? null : Number(value))

export function toCreditProduct(dto: ProductDto): CreditProduct {
  const presentation = PRESENTATION[dto.frontend_id] ?? {
    keywords: [],
    decisionTime: Number(dto.auto_decision_limit) > 0 ? '5 минут' : '1 рабочий день',
  }
  return {
    id: dto.frontend_id,
    code: dto.code,
    kind: KIND_BY_FACILITY[dto.facility],
    title: dto.name,
    description: dto.short_description,
    rateFrom: Number(dto.rate_base),
    amount: { min: Number(dto.amount_min), max: Number(dto.amount_max) },
    termMonths: { min: dto.term_min_months, max: dto.term_max_months },
    collateral: dto.collateral_kind satisfies Collateral,
    collateralRequiredFrom: toNumber(dto.collateral_required_from),
    collateralTypes: dto.collateral_types,
    purposes: dto.purposes,
    repayment: dto.repayment_options,
    legalForms: dto.allowed_legal_forms,
    requiredDocuments: dto.required_documents.map((document) => ({
      type: document.type,
      title: document.title,
      requiredFrom: toNumber(document.required_from_amount),
      legalForms: document.legal_forms,
    })),
    fieldsSchema: dto.application_fields_schema,
    startupOnly: dto.startup_only ?? false,
    ...presentation,
  }
}
