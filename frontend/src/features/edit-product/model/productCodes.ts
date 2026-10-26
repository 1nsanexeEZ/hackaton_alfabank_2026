import type { Facility } from '@/shared/api'

/**
 * Вид ссуды по форме Банка России 0409303 «Сведения о ссудах, предоставленных юридическим лицам»
 * (раздел 3, графа 1): 1.1 — кредит, 1.2 — овердрафт, 1.3 — кредитная линия с лимитом задолженности,
 * 1.4 — с лимитом выдачи. Вид выдачи продукта (facility) ложится на них один в один.
 */
export const FACILITY_LOAN_TYPE: Record<Facility, string> = {
  term_loan: '1.1',
  overdraft: '1.2',
  credit_line_revolving: '1.3',
  credit_line_non_revolving: '1.4',
}

export interface ProductCodeEntry {
  code: string
  title: string
  facility: Facility
}

/**
 * Справочник кодов продукта: новый продукт берёт код отсюда, а не придумывает его. Первые девять —
 * продукты каталога, их коды заняты; остальные — свободны. Код задаёт и вид выдачи.
 */
export const PRODUCT_CODES: readonly ProductCodeEntry[] = [
  { code: 'UNSECURED', title: 'Кредит без залога', facility: 'term_loan' },
  { code: 'SECURED', title: 'Кредит под залог', facility: 'term_loan' },
  { code: 'CREDIT_LINE', title: 'Кредитная линия', facility: 'credit_line_revolving' },
  { code: 'OVERDRAFT', title: 'Овердрафт', facility: 'overdraft' },
  { code: 'AUTO', title: 'Автокредит для бизнеса', facility: 'term_loan' },
  { code: 'MORTGAGE', title: 'Бизнес-ипотека', facility: 'term_loan' },
  { code: 'REFINANCE', title: 'Рефинансирование', facility: 'term_loan' },
  { code: 'GOV_SUPPORT', title: 'Кредит с господдержкой', facility: 'term_loan' },
  { code: 'STARTUP', title: 'Кредит на запуск бизнеса', facility: 'term_loan' },
  { code: 'EQUIPMENT', title: 'Кредит на оборудование', facility: 'term_loan' },
  { code: 'TENDER', title: 'Кредит на исполнение контракта', facility: 'term_loan' },
  { code: 'INVESTMENT', title: 'Инвестиционный кредит', facility: 'credit_line_non_revolving' },
  { code: 'REVOLVING_LINE', title: 'Возобновляемая кредитная линия', facility: 'credit_line_revolving' },
]

export const findProductCode = (code: string) => PRODUCT_CODES.find((entry) => entry.code === code)

/** Карточка на сайте по коду, как у продуктов каталога: GOV_SUPPORT → gov-support */
export const frontendIdOf = (code: string) => code.toLowerCase().replace(/_/g, '-')
