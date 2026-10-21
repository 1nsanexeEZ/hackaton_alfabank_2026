import type { CreditProduct, ProductCatalog } from './types'

/**
 * Демо-каталог с синтетическими условиями.
 * Когда появится BFF, каталог будет приходить из API, а этот файл останется для тестов и Storybook.
 */
export const DEMO_CREDIT_PRODUCTS: ProductCatalog = [
  {
    id: 'unsecured',
    kind: 'lump-sum',
    title: 'Кредит без залога',
    description: 'На пополнение оборотных средств, развитие бизнеса или рефинансирование текущих долгов.',
    rateFrom: 23.5,
    amount: { min: 300_000, max: 30_000_000 },
    termMonths: { min: 12, max: 60 },
    collateral: 'none',
    decisionTime: '5 минут',
    keywords: ['Без залога', 'Быстро', 'На любые цели'],
    tag: 'Популярный',
  },
  {
    id: 'secured',
    kind: 'lump-sum',
    title: 'Кредит под залог',
    description: 'Крупная сумма на длинный срок под залог недвижимости, транспорта или оборудования.',
    rateFrom: 21.5,
    amount: { min: 500_000, max: 150_000_000 },
    termMonths: { min: 12, max: 120 },
    collateral: 'required',
    decisionTime: '1 рабочий день',
    keywords: ['Крупная сумма', 'Надолго', 'Ставка ниже'],
  },
  {
    id: 'credit-line',
    kind: 'revolving',
    title: 'Кредитная линия',
    description: 'Берите деньги частями в пределах лимита, проценты начисляются только на использованную сумму.',
    rateFrom: 22,
    amount: { min: 1_000_000, max: 50_000_000 },
    termMonths: { min: 12, max: 36 },
    collateral: 'optional',
    decisionTime: '1 рабочий день',
    keywords: ['Частями', 'Свой лимит', 'Гибко'],
  },
  {
    id: 'overdraft',
    kind: 'revolving',
    title: 'Овердрафт',
    description: 'Платите поставщикам и налоги, даже когда на расчётном счёте временно не хватает денег.',
    rateFrom: 24,
    amount: { min: 100_000, max: 10_000_000 },
    termMonths: { min: 3, max: 12 },
    collateral: 'none',
    decisionTime: '5 минут',
    keywords: ['Кассовый разрыв', 'Сразу', 'Подушка'],
  },
]

export function findProduct(catalog: ProductCatalog, id: string): CreditProduct {
  return catalog.find((product) => product.id === id) ?? catalog[0]
}
