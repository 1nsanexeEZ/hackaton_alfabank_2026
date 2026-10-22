import type { FieldSchema, FieldsSchema } from '@/shared/api'

/**
 * Дополнительные поля заявки продукта по его JSON Schema (application_fields_schema):
 * автокредит — что покупаем, ипотека — объект, рефинансирование — список кредитов.
 * В форме всё хранится строками, в API уходит с числами.
 */
export type FieldRow = Record<string, string>
export type FieldValues = Record<string, string | FieldRow[]>

/** Подписи значений из enum — в схеме бэкенда только коды */
export const ENUM_LABEL: Record<string, string> = {
  car: 'Легковой автомобиль',
  truck: 'Грузовой транспорт',
  special: 'Спецтехника',
  office: 'Офис',
  warehouse: 'Склад',
  retail: 'Торговое помещение',
  production: 'Производство',
}

const isNumeric = (field: FieldSchema) => field.type === 'number' || field.type === 'integer'

export function parseNumber(value: string): number {
  return Number(value.replace(/\s/g, '').replace(',', '.'))
}

function emptyScalar(field: FieldSchema): string {
  return field.enum?.[0] ?? ''
}

function emptyRow(schema: FieldsSchema): FieldRow {
  return Object.fromEntries(Object.entries(schema.properties ?? {}).map(([key, field]) => [key, emptyScalar(field)]))
}

/** Значения формы из сохранённого черновика; чего нет — пустое */
export function toFormValues(schema: FieldsSchema, saved: Record<string, unknown> = {}): FieldValues {
  const values: FieldValues = {}
  for (const [key, field] of Object.entries(schema.properties ?? {})) {
    const value = saved[key]
    if (field.type === 'array' && field.items) {
      const rows = Array.isArray(value) ? (value as Record<string, unknown>[]) : []
      const items = field.items
      values[key] = rows.length
        ? rows.map((row) => ({ ...emptyRow(items), ...Object.fromEntries(Object.entries(row).map(([k, v]) => [k, String(v ?? '')])) }))
        : Array.from({ length: Math.max(field.minItems ?? 1, 1) }, () => emptyRow(items))
    } else {
      values[key] = value === undefined || value === null ? emptyScalar(field) : String(value)
    }
  }
  return values
}

export function newRow(schema: FieldsSchema): FieldRow {
  return emptyRow(schema)
}

function checkScalar(field: FieldSchema, value: string, required: boolean): string | null {
  const text = value.trim()
  if (!text) return required ? 'Заполните поле' : null
  if (isNumeric(field)) {
    const number = parseNumber(text)
    if (!Number.isFinite(number)) return 'Введите число'
    if (field.minimum !== undefined && number < field.minimum) return `Не меньше ${field.minimum}`
    if (field.maximum !== undefined && number > field.maximum) return `Не больше ${field.maximum}`
  } else if (field.minLength !== undefined && text.length < field.minLength) {
    return `Не короче ${field.minLength} символов`
  }
  return null
}

/** Ошибки по путям вида product_fields.price и product_fields.loans.0.creditor */
export function validateFieldValues(schema: FieldsSchema, values: FieldValues, prefix = 'product_fields') {
  const errors: Record<string, string> = {}
  const required = new Set(schema.required ?? [])
  for (const [key, field] of Object.entries(schema.properties ?? {})) {
    const value = values[key]
    if (field.type === 'array' && field.items && Array.isArray(value)) {
      if (required.has(key) && value.length < Math.max(field.minItems ?? 1, 1)) {
        errors[`${prefix}.${key}`] = 'Добавьте хотя бы одну запись'
      }
      value.forEach((row, index) => Object.assign(errors, validateFieldValues(field.items!, row, `${prefix}.${key}.${index}`)))
    } else if (typeof value === 'string') {
      const message = checkScalar(field, value, required.has(key))
      if (message) errors[`${prefix}.${key}`] = message
    }
  }
  return errors
}

function scalarPayload(field: FieldSchema, value: string): unknown {
  const text = value.trim()
  if (!text) return null
  return isNumeric(field) ? parseNumber(text) : text
}

/** Тело для PATCH: пустые значения — null, бэкенд удалит ключ */
export function toPayload(schema: FieldsSchema, values: FieldValues): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  for (const [key, field] of Object.entries(schema.properties ?? {})) {
    const value = values[key]
    if (field.type === 'array' && field.items && Array.isArray(value)) {
      const items = field.items
      payload[key] = value.map((row) =>
        Object.fromEntries(
          Object.entries(items.properties ?? {}).map(([name, inner]) => [name, scalarPayload(inner, row[name] ?? '')]),
        ),
      )
    } else if (typeof value === 'string') {
      payload[key] = scalarPayload(field, value)
    }
  }
  return payload
}

/** Название поля по пути из нарушения бэкенда: product_fields.loans.0.rate → «Ставка, %» */
export function fieldTitle(schema: FieldsSchema, path: string): string {
  const parts = path.split(/[.[\]]+/).filter(Boolean)
  let current: FieldsSchema | undefined = schema
  let title = 'Анкета продукта'
  for (const part of parts) {
    const field: FieldSchema | undefined = current?.properties?.[part]
    if (!field) continue
    title = field.title ?? part
    current = field.items
  }
  return title
}
