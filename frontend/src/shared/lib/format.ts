const LOCALE = 'ru-RU'

const integerFormatter = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 })
const decimalFormatter = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1 })

/** 1500000 → «1 500 000 ₽» */
export function formatMoney(value: number): string {
  return `${integerFormatter.format(Math.round(value))} ₽`
}

/** 150000000 → «150 млн ₽», 300000 → «300 тыс. ₽» */
export function formatMoneyShort(value: number): string {
  if (value >= 1_000_000_000) return `${decimalFormatter.format(value / 1_000_000_000)} млрд ₽`
  if (value >= 1_000_000) return `${decimalFormatter.format(value / 1_000_000)} млн ₽`
  if (value >= 1_000) return `${decimalFormatter.format(value / 1_000)} тыс. ₽`
  return formatMoney(value)
}

/** 21.5 → «21,5%» */
export function formatPercent(value: number): string {
  return `${decimalFormatter.format(value)}%`
}

/** pluralize(5, ['год', 'года', 'лет']) → «лет» */
export function pluralize(count: number, forms: readonly [string, string, string]): string {
  const mod100 = Math.abs(count) % 100
  const mod10 = mod100 % 10
  if (mod100 > 10 && mod100 < 20) return forms[2]
  if (mod10 === 1) return forms[0]
  if (mod10 >= 2 && mod10 <= 4) return forms[1]
  return forms[2]
}

const YEAR_FORMS = ['год', 'года', 'лет'] as const
const MONTH_FORMS = ['месяц', 'месяца', 'месяцев'] as const

/** 30 → «2 года 6 мес.», 24 → «2 года», 9 → «9 месяцев» */
export function formatTerm(months: number): string {
  const years = Math.floor(months / 12)
  const rest = months % 12
  if (years === 0) return `${rest} ${pluralize(rest, MONTH_FORMS)}`
  const yearsPart = `${years} ${pluralize(years, YEAR_FORMS)}`
  return rest === 0 ? yearsPart : `${yearsPart} ${rest} мес.`
}

/** Оставляет в строке только цифры: «1 500 000 ₽» → «1500000» */
export function onlyDigits(value: string): string {
  return value.replace(/\D/g, '')
}
