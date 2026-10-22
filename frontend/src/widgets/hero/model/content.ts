import { BadgePercent, Banknote, CalendarDays, Timer, type LucideIcon } from 'lucide-vue-next'

import type { ApplicationPreview } from '@/entities/application'
import type { CreditProduct } from '@/entities/credit-product'
import { formatMoneyShort, formatPercent, formatTerm } from '@/shared/lib'

export interface HeroStat {
  /** null — каталог ещё грузится */
  value: string | null
  caption: string
  icon: LucideIcon
}

/** Ключевые цифры считаются из каталога API, чтобы витрина не расходилась с условиями продуктов */
export function heroStats(products: readonly CreditProduct[] | null): HeroStat[] {
  const list = products ?? []
  const pick = (format: () => string) => (list.length ? format() : null)
  return [
    { value: pick(() => `от ${formatPercent(Math.min(...list.map((item) => item.rateFrom)))}`), caption: 'Ставка', icon: BadgePercent },
    { value: pick(() => `до ${formatTerm(Math.max(...list.map((item) => item.termMonths.max)))}`), caption: 'Срок', icon: CalendarDays },
    { value: pick(() => `до ${formatMoneyShort(Math.max(...list.map((item) => item.amount.max)))}`), caption: 'Сумма', icon: Banknote },
    { value: '5 минут', caption: 'Предварительное решение', icon: Timer },
  ]
}

/** Иллюстрация на первом экране: так выглядит заявка в кабинете */
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
