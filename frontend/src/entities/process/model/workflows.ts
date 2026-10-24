/** Маршруты процесса (backend/src/modules/process/workflows): код — `<вид>_v<версия>` */
const WORKFLOW_KIND: Record<string, string> = {
  express: 'Экспресс: авторешение без залога',
  standard: 'Стандартный',
  secured: 'С залогом: оценка залога перед скорингом',
  mortgage: 'Бизнес-ипотека: решает специалист',
  startup: 'Стартап: проектная оценка',
}

/** «Стандартный · v2»; неизвестный вид — код как есть */
export function workflowTitle(code: string): string {
  const match = /^(.+)_v(\d+)$/.exec(code)
  if (!match) return code
  const [, kind = '', version] = match
  return `${WORKFLOW_KIND[kind] ?? kind} · v${version}`
}
