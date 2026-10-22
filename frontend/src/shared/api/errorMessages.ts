/**
 * Тексты ошибок бэкенда для людей. Бэкенд пишет message по-английски (это текст для логов),
 * а что именно случилось — в details.code. Поэтому выбираем текст по коду, а не показываем message.
 * Коды — из ответов модулей applications, products, clients и identity.
 */
const BY_DETAILS_CODE: Record<string, string> = {
  version_conflict: 'Заявку успели изменить — обновите страницу',
  duplicate_active: 'По этому продукту у компании уже есть заявка в работе — дождитесь решения по ней',
  offer_expired: 'Срок действия предложения истёк',
  not_submitted: 'Заявка ещё не отправлена',
  info_request_closed: 'Запрос банка уже закрыт',
  confirmed: 'Документ уже загружен',
  bad_size: 'Файл пустой или больше 20 МБ',
  content_type_not_allowed: 'Такой тип файла не принимается',
  unexpected_document: 'Этот документ для заявки не нужен',
  upload_mismatch: 'Файл загрузился не полностью — выберите его ещё раз',
  upload_missing: 'Файл ещё не дошёл до хранилища — попробуйте ещё раз',
  invalid_password: 'Неверный пароль',
  org_permission_required: 'Недостаточно прав в компании для этого действия',
  already_member: 'Этот человек уже участник компании',
  account_not_found: 'Нет учётной записи с таким email или телефоном',
  cannot_issue_power_of_attorney: 'Доверенность выдаёт руководитель, полномочия которого подтверждены реестром',
  self_power_of_attorney: 'Доверенность нельзя выдать самому себе',
  expired: 'Срок доверенности уже истёк',
  period_not_closed: 'Этот период ещё не закончился — отчёт за него подать нельзя',
  report_exists: 'Отчёт за этот период уже отправляется, попробуйте ещё раз',
  manager_required: 'В компании должен остаться участник, который управляет составом',
}

const BY_STATUS: Record<number, string> = {
  403: 'Недостаточно прав для этого действия',
  404: 'Не нашли запрошенные данные — обновите страницу',
  409: 'Данные успели измениться — обновите страницу',
  422: 'Проверьте введённые данные',
  503: 'Сервис временно недоступен, попробуйте позже',
}

interface Reason {
  message?: string
  passed?: boolean
}

/** Причины, по которым компания не подходит под продукт: бэкенд уже пишет их по-русски */
export function eligibilityMessage(reasons: readonly Reason[]): string {
  const failed = reasons.filter((reason) => reason.passed !== true && reason.message).map((reason) => reason.message)
  return failed.length ? `Компания не подходит под продукт: ${failed.join('; ')}` : 'Компания не подходит под продукт'
}

export function humanMessage(
  status: number,
  message: string | undefined,
  details: Record<string, unknown>,
  /** Был ли у запроса токен: 401 без токена — это неверный логин или пароль, с токеном — истёкшая сессия */
  authorized: boolean,
): string {
  const code = typeof details.code === 'string' ? details.code : undefined
  if (code === 'not_eligible' && Array.isArray(details.reasons)) return eligibilityMessage(details.reasons as Reason[])
  if (code && BY_DETAILS_CODE[code]) return BY_DETAILS_CODE[code]
  // Часть сообщений бэкенд уже пишет по-русски — их показываем как есть
  if (message && /[а-яё]/i.test(message)) return message
  if (status === 401) return authorized ? 'Сессия истекла — войдите снова' : 'Неверный логин или пароль'
  if (status >= 500 && status !== 503) return 'Ошибка сервера, попробуйте позже'
  return BY_STATUS[status] ?? 'Запрос не выполнен'
}
