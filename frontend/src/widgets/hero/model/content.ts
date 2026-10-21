import { BadgePercent, Banknote, CalendarDays, Timer, type LucideIcon } from 'lucide-vue-next'

import type { ApplicationPreview } from '@/entities/application'
import { DEMO_CREDIT_PRODUCTS } from '@/entities/credit-product'
import { formatMoneyShort, formatPercent, formatTerm } from '@/shared/lib'

const minRate = Math.min(...DEMO_CREDIT_PRODUCTS.map((product) => product.rateFrom))
const maxTerm = Math.max(...DEMO_CREDIT_PRODUCTS.map((product) => product.termMonths.max))
const maxAmount = Math.max(...DEMO_CREDIT_PRODUCTS.map((product) => product.amount.max))

/** Ключевые цифры считаются из каталога, чтобы витрина не расходилась с условиями продуктов */
export const HERO_STATS: readonly { value: string; caption: string; icon: LucideIcon }[] = [
  { value: `от ${formatPercent(minRate)}`, caption: 'Ставка', icon: BadgePercent },
  { value: `до ${formatTerm(maxTerm)}`, caption: 'Срок', icon: CalendarDays },
  { value: `до ${formatMoneyShort(maxAmount)}`, caption: 'Сумма', icon: Banknote },
  { value: '5 минут', caption: 'Предварительное решение', icon: Timer },
]

export const HERO_DEMO_APPLICATION: ApplicationPreview = {
  number: 'ЗК-104582',
  productTitle: 'Кредит без залога',
  amount: 3_000_000,
  termMonths: 24,
  status: 'scoring',
  stages: [
    { title: 'Заявка отправлена', caption: 'Сегодня, 10:42', state: 'done' },
    { title: 'Проверка данных', caption: 'ЕГРЮЛ, ФНС, бюро кредитных историй', state: 'done' },
    { title: 'Оценка риска', caption: 'Обычно до 5 минут', state: 'current' },
    { title: 'Решение банка', state: 'pending' },
    { title: 'Подписание и выдача', state: 'pending' },
  ],
}
