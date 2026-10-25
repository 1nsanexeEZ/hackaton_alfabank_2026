/** Числа карточки андеррайтера: рубли строками из API — в числа, миллионы для таблиц и графиков, изменение за период */

/** Сумма строкой из API → число; null и пустая строка — нет значения */
export const amount = (value: string | number | null | undefined): number | null =>
  value === null || value === undefined || value === '' ? null : Number(value)

const millionFormatter = new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
const smallFormatter = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 })

/** Значение для таблиц «млн ₽»: 48 000 000 → «48,0», 380 000 → «0,38», 0 → «0» */
export function millions(value: number): string {
  if (value === 0) return '0'
  const share = value / 1_000_000
  return Math.abs(share) < 1 ? smallFormatter.format(share) : millionFormatter.format(share)
}

/** Изменение к прошлому периоду: «+9%», «−10%»; null — сравнивать не с чем */
export function change(current: number, previous: number | null | undefined): { text: string; sign: -1 | 0 | 1 } | null {
  if (!previous) return null
  const share = Math.round(((current - previous) / Math.abs(previous)) * 100)
  if (share > 0) return { text: `+${share}%`, sign: 1 }
  if (share < 0) return { text: `−${Math.abs(share)}%`, sign: -1 }
  return { text: '0%', sign: 0 }
}

/** Верх оси графика с запасом: 4,26 млн → 5 млн, 1,3 → 1,5 */
export function niceCeil(value: number): number {
  if (value <= 0) return 1
  const power = 10 ** Math.floor(Math.log10(value))
  const step = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10].find((candidate) => candidate * power >= value) ?? 10
  return step * power
}

const MONTH_SHORT = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'] as const

/** «2025-10» → «окт»; withYear — «окт 25» */
export function monthLabel(month: string, withYear = false): string {
  const name = MONTH_SHORT[Number(month.slice(5, 7)) - 1] ?? month
  return withYear ? `${name} ${month.slice(2, 4)}` : name
}

/** Доля в процентах для ширины полосы, в пределах 0–100 */
export const share = (part: number, whole: number): number => (whole > 0 ? Math.min(100, Math.max(0, (part / whole) * 100)) : 0)
