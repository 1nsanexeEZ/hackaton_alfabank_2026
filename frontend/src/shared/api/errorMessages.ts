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
  identity_locked: 'ФИО подтверждено банком — изменить его может только сотрудник банка',
  contract_not_ready: 'Договор появится, когда заявку одобрят и вы примете предложение',
  offer_changed: 'Условия предложения изменились — проверьте договор ещё раз и подпишите',
  document_pending: 'Договор ещё формируется — подождите несколько секунд',
  document_changed: 'Договор обновился, пока вы его читали, — проверьте новую версию и подпишите ещё раз',
  rules_outdated: 'Правила электронного взаимодействия обновились — прочитайте новую редакцию и подтвердите согласие',
  document_not_found: 'Документ не найден в архиве банка',
  not_a_pdf: 'Это не PDF-файл — выберите договор в формате PDF',
  file_too_large: 'Файл больше 10 МБ',
  product_not_available: 'Продукт сейчас не принимает заявки',
  org_permission_required: 'Недостаточно прав в компании для этого действия',
  already_member: 'Этот человек уже участник компании',
  account_not_found: 'Нет учётной записи с таким email или телефоном',
  cannot_issue_power_of_attorney: 'Доверенность выдаёт руководитель, полномочия которого подтверждены реестром',
  self_power_of_attorney: 'Доверенность нельзя выдать самому себе',
  expired: 'Срок доверенности уже истёк',
  period_not_closed: 'Этот период ещё не закончился — отчёт за него подать нельзя',
  report_exists: 'Отчёт за этот период уже отправляется, попробуйте ещё раз',
  manager_required: 'В компании должен остаться участник, который управляет составом',
  last_manager: 'В компании должен остаться участник, который управляет составом',
  owner_exists: 'У ИП может быть только один владелец',
  entrepreneur_owner_fixed: 'Владельца ИП нельзя сменить или удалить',
  not_a_member: 'Менять данные компании может только её участник',
  registry_not_found: 'В реестре нет компании с таким ИНН',
  consent_required: 'Нужно согласие учредителя на запрос его кредитной истории',
  founder_not_found: 'Учредителя по реестру нет среди участников компании — добавьте его в «Компании»',
  out_of_range: 'Сумма или срок вне рамок продукта',
  not_offered: 'Такая схема погашения для продукта недоступна',
  bad_registry_data: 'Реестр ответил данными, которые не удалось разобрать, — попробуйте позже',
  business_plan_required: 'Сначала заполните бизнес-план и финмодель',
  product_not_eligible: 'Кредит на запуск бизнеса компании не подходит: у неё уже есть обороты',
  no_guarantee: 'Без гарантии доля гарантии должна быть нулевой',
  horizon: 'В финмодели должно быть ровно 24 месяца',
  already_taken: 'Обращение уже взял другой сотрудник',
  not_taken: 'Сначала возьмите обращение',
  not_assignee: 'Обращение ведёт другой сотрудник',
  not_author: 'Писать в обращение может только его автор',
  ticket_closed: 'Обращение закрыто — задайте вопрос заново',
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
