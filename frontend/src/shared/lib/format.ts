const LOCALE = 'ru-RU'

const integerFormatter = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 })
const decimalFormatter = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 1 })
const probabilityFormatter = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

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

/** Вероятность-доля: 0.0421 → «4,21%» — для PD моделей, где важны сотые */
export function formatProbability(share: number): string {
  return `${probabilityFormatter.format(share * 100)}%`
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
/** «до 3 лет», «до 1 года», «до 18 месяцев» — срок как предел */
export function formatTermLimit(months: number): string {
  if (months % 12 === 0) {
    const years = months / 12
    return `до ${years} ${years % 10 === 1 && years % 100 !== 11 ? 'года' : 'лет'}`
  }
  return `до ${months} ${months % 10 === 1 && months % 100 !== 11 ? 'месяца' : 'месяцев'}`
}

export function onlyDigits(value: string): string {
  return value.replace(/\D/g, '')
}

const dateFormatter = new Intl.DateTimeFormat(LOCALE, { day: 'numeric', month: 'short', year: 'numeric' })
const dateTimeFormatter = new Intl.DateTimeFormat(LOCALE, {
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
})
const relativeFormatter = new Intl.RelativeTimeFormat(LOCALE, { numeric: 'auto' })

/** «14 мар. 2017 г.» */
export function formatDate(value: string | Date): string {
  return dateFormatter.format(new Date(value))
}

/** «21 окт., 14:05» */
export function formatDateTime(value: string | Date): string {
  return dateTimeFormatter.format(new Date(value))
}

/** «3 часа назад», «через 5 часов» */
export function formatRelativeTime(value: string | Date, now = Date.now()): string {
  const minutes = Math.round((new Date(value).getTime() - now) / 60_000)
  if (Math.abs(minutes) < 60) return relativeFormatter.format(minutes, 'minute')
  const hours = Math.round(minutes / 60)
  if (Math.abs(hours) < 48) return relativeFormatter.format(hours, 'hour')
  return relativeFormatter.format(Math.round(hours / 24), 'day')
}
