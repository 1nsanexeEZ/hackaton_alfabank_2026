import type { ApiViolation } from '@/shared/api'

export type WizardStep = 'terms' | 'details' | 'consents' | 'done'

export interface ViolationView {
  message: string
  /** Шаг мастера, где это исправляется */
  step: Exclude<WizardStep, 'done'>
}

const FIELD_LABEL: Record<string, string> = {
  'request.amount': 'сумма кредита',
  'request.term_months': 'срок',
  'request.purpose': 'цель кредита',
  collateral: 'залог',
  'collateral.owner_party.name': 'владелец залога',
  'collateral.owner_party.inn': 'ИНН владельца залога',
  beneficiary: 'в чьих интересах вы действуете',
  'beneficiary.beneficiary.name': 'в чьих интересах вы действуете',
  'beneficiary.beneficiary.inn': 'ИНН того, в чьих интересах вы действуете',
  'beneficiary.basis': 'основание действовать в интересах третьего лица',
  'beneficiary.beneficiary.country': 'страна того, в чьих интересах вы действуете',
  'collateral.owner_party.country': 'страна владельца залога',
  beneficial_owners: 'бенефициары компании',
  'consents.personal_data': 'согласие на обработку персональных данных',
  'consents.credit_bureau': 'согласие на запрос в бюро кредитных историй',
}

function stepOf(field: string): ViolationView['step'] {
  if (field.startsWith('request.') || field === 'product_code') return 'terms'
  if (field.startsWith('consents.') || field.startsWith('beneficiary') || field.startsWith('beneficial_owners')) return 'consents'
  return 'details'
}

/** Нарушения комплектности бэкенда (GET …/completeness, 422 на submit) — понятным текстом */
export function describeViolations(
  violations: ApiViolation[],
  context: { documentTitle: (type: string) => string; fieldTitle: (path: string) => string },
): ViolationView[] {
  return violations.map(({ code, field }) => {
    const step = stepOf(field)
    if (code === 'duplicate_active') {
      return { step, message: 'По этому продукту у компании уже есть заявка в работе — дождитесь решения по ней' }
    }
    if (field.startsWith('documents.')) {
      return { step, message: `Не загружен документ: ${context.documentTitle(field.slice('documents.'.length))}` }
    }
    const label = field.startsWith('product_fields.') ? `«${context.fieldTitle(field)}»` : (FIELD_LABEL[field] ?? field)
    if (code === 'missing') return { step, message: `Не заполнено: ${label}` }
    if (code === 'out_of_range') return { step, message: `Вне условий продукта: ${label}` }
    if (code === 'bad_checksum') return { step, message: `Неверный ИНН: ${label}` }
    return { step, message: `Проверьте: ${label}` }
  })
}
