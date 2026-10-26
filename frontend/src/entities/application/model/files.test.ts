import { describe, expect, it } from 'vitest'

import { contentTypeOf, documentFormat, fileProblem, MAX_FILE_BYTES } from './documentFormats'
import { STATEMENT_SAMPLE, statementProblem } from './statement'

const file = (content: string, name: string, type = '') => new File([content], name, { type })

describe('документы заявки: формат и размер', () => {
  it('выписка — только CSV, остальное — PDF, JPG или PNG', () => {
    expect(documentFormat('bank_statement').kinds).toBe('CSV')
    expect(documentFormat('financial_report').kinds).toBe('PDF, JPG или PNG')
  })

  it('тип файла без type от браузера — по расширению', () => {
    expect(contentTypeOf(file('x', 'Отчёт.PDF'))).toBe('application/pdf')
    expect(contentTypeOf(file('x', 'scan.jpeg'))).toBe('image/jpeg')
    expect(contentTypeOf(file('x', 'data.bin'))).toBe('application/octet-stream')
    expect(contentTypeOf(file('x', 'a.csv', 'application/vnd.ms-excel'))).toBe('application/vnd.ms-excel')
  })

  it('пустой, слишком большой или не того формата — понятная причина', () => {
    expect(fileProblem('financial_report', file('', 'a.pdf'))).toBe('Файл пустой')
    const big = { size: MAX_FILE_BYTES + 1, name: 'a.pdf', type: 'application/pdf' } as File
    expect(fileProblem('financial_report', big)).toBe('Файл больше 20 МБ')
    expect(fileProblem('bank_statement', file('x', 'a.pdf'))).toBe('Подойдёт только CSV')
    expect(fileProblem('bank_statement', file('x', 'a.csv', 'application/vnd.ms-excel'))).toBeNull()
    expect(fileProblem('financial_report', file('x', 'a.png'))).toBeNull()
  })
})

describe('выписка по счёту для прогноза кассового разрыва (S-2, S-5)', () => {
  it('образец из подсказки проходит проверку, BOM в начале допускается', async () => {
    expect(await statementProblem(file(STATEMENT_SAMPLE, 'statement.csv'))).toBeNull()
    expect(await statementProblem(file(`\ufeff${STATEMENT_SAMPLE}\n`, 'statement.csv'))).toBeNull()
  })

  it('разделитель — точка с запятой', async () => {
    expect(await statementProblem(file('date,amount\n2026-01-05,100', 's.csv'))).toBe('Разделитель колонок — точка с запятой «;», а не запятая')
  })

  it('обязательные колонки date и amount', async () => {
    expect(await statementProblem(file('day;sum\n', 's.csv'))).toBe('В первой строке нет колонок date и amount — см. формат выписки')
    expect(await statementProblem(file('date;purpose\n', 's.csv'))).toBe('В первой строке нет колонок amount — см. формат выписки')
  })

  it('ошибка в строке — с её номером', async () => {
    expect(await statementProblem(file('date;amount\n2026-01-05;100\n05.01.2026;100', 's.csv'))).toBe(
      'Строка 3: дата «05.01.2026» не в формате ГГГГ-ММ-ДД',
    )
    expect(await statementProblem(file('date;amount\r\n2026-01-05;1 500,00', 's.csv'))).toBe(
      'Строка 2: сумма «1 500,00» — нужна точка, без пробелов и валюты, например 1500.00',
    )
  })
})
