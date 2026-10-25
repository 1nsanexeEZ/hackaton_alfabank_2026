import { ApiError, type VersionBody, type VersionBodyError } from '@/shared/api'

/** Путь к полю документа версии: ключи объектов и индексы массивов, как в details.errors бэкенда */
export type DocPath = readonly (string | number)[]

export const pathKey = (path: DocPath) => path.join('.')

export function getAt(body: unknown, path: DocPath): unknown {
  let current: unknown = body
  for (const key of path) {
    if (current === null || typeof current !== 'object') return undefined
    current = (current as Record<string | number, unknown>)[key]
  }
  return current
}

export const hasAt = (body: unknown, path: DocPath) => getAt(body, path) !== undefined

/** Меняет поле на месте; родитель должен существовать — новых веток документа формы не создают */
export function setAt(body: VersionBody, path: DocPath, value: unknown): void {
  const parent = getAt(body, path.slice(0, -1))
  if (parent === null || typeof parent !== 'object') return
  ;(parent as Record<string | number, unknown>)[path[path.length - 1]!] = value
}

/** 422 документа: список { path, message } в details.errors; иначе — пусто */
export function bodyErrors(caught: unknown): VersionBodyError[] {
  if (!(caught instanceof ApiError) || caught.status !== 422) return []
  const errors = caught.details.errors
  if (!Array.isArray(errors)) return []
  return errors.filter(
    (item): item is VersionBodyError =>
      typeof item === 'object' && item !== null && typeof item.path === 'string' && typeof item.message === 'string',
  )
}
