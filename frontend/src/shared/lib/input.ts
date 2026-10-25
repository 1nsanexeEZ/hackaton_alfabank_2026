/** Что можно вводить в поле: только цифры, число с дробной частью или сумму с разделителями тысяч */
export type InputFilter = 'digits' | 'decimal' | 'amount'

const NBSP = ' '

/** «3 000 000 ₽», «3000000.00», «23,5 %» → число; пусто или без цифр → null */
export function parseNumber(text: string): number | null {
  const cleaned = text.replace(/[\s  ₽%]/g, '').replace(',', '.')
  const match = cleaned.match(/-?\d+(\.\d+)?/)
  if (!match) return null
  const value = Number(match[0])
  return Number.isFinite(value) ? value : null
}

/** «3000000» → «3 000 000» (неразрывные пробелы, как в formatMoney) */
export function groupThousands(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP)
}

/** Оставляет в строке только допустимое для поля; вставка «3 000 000 ₽» в сумму даёт «3 000 000» */
export function sanitizeInput(value: string, filter: InputFilter): string {
  if (filter === 'digits') return value.replace(/\D/g, '')
  if (filter === 'amount') {
    // дробная часть суммы при вставке отбрасывается: «3000000.00» — это три миллиона, а не триста миллионов
    const whole = value.replace(/[\s  ]/g, '').split(/[.,]/)[0] ?? ''
    return groupThousands(whole.replace(/\D/g, '').replace(/^0+(?=\d)/, ''))
  }
  // decimal: цифры и один разделитель, не больше двух знаков после него
  const normalized = value.replace(/[^\d.,]/g, '').replace('.', ',')
  const [whole = '', ...rest] = normalized.split(',')
  if (!rest.length) return whole
  return `${whole},${rest.join('').replace(/,/g, '').slice(0, 2)}`
}

/** Клавиатура телефона под фильтр поля */
export function inputModeFor(filter: InputFilter): 'numeric' | 'decimal' {
  return filter === 'decimal' ? 'decimal' : 'numeric'
}
