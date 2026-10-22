/**
 * Какие файлы принимает бэкенд (backend/src/modules/applications/domain/entities.py):
 * до 20 МБ, PDF, JPG или PNG; выписка по счёту — только CSV, её разбирают для прогноза кассового разрыва.
 */
export const MAX_FILE_BYTES = 20 * 1024 * 1024

export interface DocumentFormat {
  /** Для input[type=file] */
  accept: string
  contentTypes: readonly string[]
  /** «PDF, JPG или PNG» — для подсказки и ошибки */
  kinds: string
}

const DEFAULT_FORMAT: DocumentFormat = {
  accept: '.pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png',
  contentTypes: ['application/pdf', 'image/jpeg', 'image/png'],
  kinds: 'PDF, JPG или PNG',
}

const FORMAT_BY_TYPE: Record<string, DocumentFormat> = {
  // Windows-браузеры отдают .csv как application/vnd.ms-excel
  bank_statement: { accept: '.csv,text/csv', contentTypes: ['text/csv', 'application/vnd.ms-excel'], kinds: 'CSV' },
}

const TYPE_BY_EXTENSION: Record<string, string> = {
  pdf: 'application/pdf',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  csv: 'text/csv',
}

export function documentFormat(type: string): DocumentFormat {
  return FORMAT_BY_TYPE[type] ?? DEFAULT_FORMAT
}

/** Тип файла для бэкенда: браузер не всегда его знает — тогда определяем по расширению */
export function contentTypeOf(file: File): string {
  if (file.type) return file.type
  const extension = file.name.split('.').pop()?.toLowerCase() ?? ''
  return TYPE_BY_EXTENSION[extension] ?? 'application/octet-stream'
}

/** Почему файл не подойдёт; null — можно загружать */
export function fileProblem(type: string, file: File): string | null {
  if (!file.size) return 'Файл пустой'
  if (file.size > MAX_FILE_BYTES) return 'Файл больше 20 МБ'
  const format = documentFormat(type)
  return format.contentTypes.includes(contentTypeOf(file)) ? null : `Подойдёт только ${format.kinds}`
}
