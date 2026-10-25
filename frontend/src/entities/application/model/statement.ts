/**
 * Выписка по счёту для прогноза кассового разрыва (docs/modules/enrichment.md, «Формат выписки»):
 * CSV в UTF-8, разделитель «;», первая строка — заголовок, обязательны колонки date и amount.
 * Файл с ошибкой бэкенд не отклоняет, а молча не разбирает — прогноза не будет. Поэтому те же правила
 * проверяем до загрузки и показываем клиенту номер строки.
 */
export const STATEMENT_TYPE = 'bank_statement'

export const STATEMENT_COLUMNS: readonly { name: string; required: boolean; format: string; example: string }[] = [
  { name: 'date', required: true, format: 'дата операции ГГГГ-ММ-ДД', example: '2026-01-05' },
  { name: 'amount', required: true, format: 'сумма в рублях через точку, без пробелов и валюты; минус — списание', example: '-48000.00' },
  { name: 'counterparty_inn', required: false, format: 'ИНН контрагента', example: '7701234567' },
  { name: 'counterparty_name', required: false, format: 'наименование контрагента', example: 'ООО Поставщик' },
  { name: 'purpose', required: false, format: 'назначение платежа', example: 'Оплата по счёту 12' },
]

export const STATEMENT_SAMPLE = [
  'date;amount;counterparty_inn;counterparty_name;purpose',
  '2026-01-05;150000.00;7701234567;ООО Поставщик;Оплата по счёту 12',
  '2026-01-06;-48000.00;7709876543;ООО Аренда;Аренда за январь',
  '2026-01-15;-120000.00;;Зарплата сотрудникам;Выплата зарплаты',
].join('\n')

const DATE = /^\d{4}-\d{2}-\d{2}$/
const AMOUNT = /^-?\d+(\.\d+)?$/

/** Почему выписку не разберут; null — формат верный */
export async function statementProblem(file: File): Promise<string | null> {
  let text: string
  try {
    text = await file.text()
  } catch {
    return null // Не прочитали в браузере — пусть решает бэкенд
  }
  // BOM в начале файла допускается — убираем по коду символа
  const lines = (text.charCodeAt(0) === 0xfeff ? text.slice(1) : text).split(/\r?\n/)
  const header = (lines[0] ?? '').split(';').map((cell) => cell.trim().toLowerCase())
  if (header.length < 2 && (lines[0] ?? '').includes(',')) return 'Разделитель колонок — точка с запятой «;», а не запятая'
  const date = header.indexOf('date')
  const amount = header.indexOf('amount')
  const missing = [date < 0 && 'date', amount < 0 && 'amount'].filter(Boolean)
  if (missing.length) return `В первой строке нет колонок ${missing.join(' и ')} — см. формат выписки`
  for (let index = 1; index < lines.length; index++) {
    const line = lines[index]!
    if (!line.trim()) continue
    const cells = line.split(';')
    const day = (cells[date] ?? '').trim()
    const sum = (cells[amount] ?? '').trim()
    if (!DATE.test(day)) return `Строка ${index + 1}: дата «${day}» не в формате ГГГГ-ММ-ДД`
    if (!AMOUNT.test(sum)) return `Строка ${index + 1}: сумма «${sum}» — нужна точка, без пробелов и валюты, например 1500.00`
  }
  return null
}
