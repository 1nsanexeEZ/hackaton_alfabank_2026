import type { ProductDto } from '@/shared/api'

import type { Collateral, CreditProduct, ProductKind } from './types'

const KIND_BY_FACILITY: Record<ProductDto['facility'], ProductKind> = {
  term_loan: 'lump-sum',
  credit_line_revolving: 'revolving',
  credit_line_non_revolving: 'revolving',
  overdraft: 'revolving',
}

const toNumber = (value: string | null) => (value === null ? null : Number(value))

export function toCreditProduct(dto: ProductDto): CreditProduct {
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
    // Витрина ведётся в каталоге банка; время решения не задано — по тому, решает ли автоматика
    keywords: dto.keywords ?? [],
    decisionTime: dto.decision_time ?? (Number(dto.auto_decision_limit) > 0 ? '5 минут' : '1 рабочий день'),
    tag: dto.tag ?? undefined,
  }
}
