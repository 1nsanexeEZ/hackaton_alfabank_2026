/**
 * Подписи для рабочего места андеррайтера. Коды — из модулей бэкенда: маршруты и стоп-факторы —
 * decision/infrastructure/config/explanations_ru.yaml, факторы — scoring/infrastructure/config/scorecard_v1.yaml,
 * флаги — scoring/domain/model.py RiskFlag. Неизвестный код показываем как есть.
 * Грейды — шкала A–J модели PD (scoring/infrastructure/config/pd_model_v2.yaml).
 */

/** Почему решение не принято автоматически или почему отказ */
export const REASON_LABEL: Record<string, string> = {
  ROUTE_AMOUNT_OVER_AUTO_LIMIT: 'Сумма выше лимита авторешения',
  ROUTE_GRADE_D: 'Грейд D — смотрим финансовое положение',
  ROUTE_VERIFICATION_MISMATCH: 'Данные компании расходятся с ЕГРЮЛ',
  ROUTE_REVENUE_MISMATCH: 'Выписка не подтвердила заявленную выручку',
  ROUTE_SOURCES_FAILED: 'Источник данных не ответил',
  ROUTE_MASS_ADDRESS: 'Адрес массовой регистрации',
  ROUTE_TAX_ARREARS: 'Недоимка по налогам',
  ROUTE_RISK_MATRIX: 'Сумма выше авторешения для грейда',
  ROUTE_SOFT_TRIGGER: 'Сработал мягкий триггер',
  STOP_LIQUIDATION: 'Компания ликвидируется',
  STOP_BANKRUPTCY: 'Процедура банкротства',
  STOP_BANKRUPTCY_MESSAGE: 'Сообщение о банкротстве',
  STOP_DISQUALIFIED_HEAD: 'Руководитель дисквалифицирован',
  STOP_OVERDUE_90: 'Просрочка больше 90 дней',
  STOP_CURRENT_OVERDUE: 'Текущая просрочка в БКИ',
  STOP_HEAD_OVERDUE: 'Просрочка руководителя в БКИ',
  STOP_ACCOUNT_BLOCKS: 'Операции по счетам приостановлены',
  STOP_TAX_ARREARS: 'Крупная недоимка по налогам',
  STOP_LARGE_ENFORCEMENT: 'Крупные исполнительные производства',
  STOP_LARGE_LAWSUITS: 'Крупные иски к компании',
  STOP_NEGATIVE_EQUITY: 'Отрицательный собственный капитал',
  STOP_MASS_ADDRESS: 'Адрес массовой регистрации',
  STOP_FORBIDDEN_OKVED: 'Вид деятельности не кредитуется',
  STOP_FOUNDER_PRESCREEN: 'Нет предскрининга учредителя',
  STOP_RISK_MATRIX: 'Сумма выше допустимой для грейда',
  STOP_GRADE_E: 'Грейд E',
  INFO_REVENUE_NOT_CONFIRMED: 'Нужна выписка для подтверждения выручки',
  LIMIT_BY_PRODUCT: 'Лимит продукта',
  LIMIT_BY_REVENUE: 'Лимит по выручке',
  LIMIT_BY_LTV: 'Лимит по стоимости залога',
  LIMIT_BY_PAYMENT_CAPACITY: 'Лимит по платёжеспособности',
  LIMIT_BY_TURNOVER: 'Лимит по оборотам',
  LIMIT_BY_GRADE: 'Лимит по грейду',
  LIMIT_BY_GROUP: 'Лимит с учётом кредитов группы',
  LIMIT_BELOW_PRODUCT_MIN: 'Доступная сумма ниже минимума продукта',
  TERM_ADJUSTED: 'Срок подобран под посильный платёж',
  CASH_GAP_FORECAST: 'Прогноз кассового разрыва',
}

export const FACTOR_LABEL: Record<string, string> = {
  business_age: 'Возраст бизнеса',
  revenue_trend: 'Динамика выручки',
  debt_load: 'Долговая нагрузка',
  bureau_overdue: 'Просрочки в БКИ',
  bureau_inquiries: 'Запросы в БКИ за 30 дней',
  tax_arrears: 'Недоимка ФНС',
  industry_risk: 'Отраслевой риск',
  amount_to_revenue: 'Сумма к выручке',
  revenue_consistency: 'Заявленная выручка и ФНС',
  verification: 'Сверка с ЕГРЮЛ',
  collateral_coverage: 'Покрытие залогом',
  cash_gap: 'Кассовый разрыв',
}

export const FLAG_LABEL: Record<string, string> = {
  revenue_mismatch: 'Выручка не сходится',
  verification_mismatch: 'Расхождение с ЕГРЮЛ',
  bureau_unavailable: 'БКИ не ответило',
  thin_file: 'Нет кредитной истории',
  mass_address: 'Массовый адрес',
  cash_gap: 'Кассовый разрыв',
}

export const SOURCE_LABEL: Record<string, string> = {
  egrul: 'ЕГРЮЛ / ЕГРИП',
  fns: 'ФНС',
  bki: 'Бюро кредитных историй',
  bki_head: 'БКИ руководителя',
  gir_bo: 'ГИР БО',
  kontur: 'Контур',
  statement: 'Выписка по счёту',
}

/** Лимиты движка (LimitsDTO) по ключу; binding называет один из них */
export const LIMIT_LABEL: Record<string, string> = {
  by_product: 'Лимит продукта',
  by_revenue: 'По выручке',
  by_turnover: 'По оборотам',
  by_capacity: 'По платёжеспособности',
  by_grade: 'По грейду',
  by_group: 'С учётом кредитов группы',
  by_ltv: 'По залогу',
}

export const SEGMENT_LABEL: Record<string, string> = {
  legal_entity: 'юрлицо',
  entrepreneur: 'ИП',
  new_client: 'новый клиент',
}

export const RELIABILITY: Record<string, { label: string; tone: 'success' | 'warning' | 'brand' }> = {
  green: { label: 'Надёжность высокая', tone: 'success' },
  yellow: { label: 'Есть замечания', tone: 'warning' },
  red: { label: 'Надёжность низкая', tone: 'brand' },
}

export const OUTCOME_LABEL: Record<string, { label: string; tone: 'success' | 'warning' | 'info' | 'brand' | 'neutral' }> = {
  APPROVE: { label: 'Одобрить', tone: 'success' },
  COUNTER_OFFER: { label: 'Контрпредложение', tone: 'warning' },
  REQUEST_INFO: { label: 'Запрос информации', tone: 'info' },
  MANUAL_REVIEW: { label: 'Ручное рассмотрение', tone: 'info' },
  REJECT: { label: 'Отказ', tone: 'brand' },
}

export const GRADE_TONE: Record<string, 'success' | 'info' | 'warning' | 'brand'> = {
  A: 'success',
  B: 'success',
  C: 'info',
  D: 'warning',
  E: 'warning',
  F: 'warning',
  G: 'warning',
  H: 'brand',
  I: 'brand',
  J: 'brand',
}

export const TASK_STATUS_LABEL: Record<string, string> = {
  open: 'Ждёт специалиста',
  in_progress: 'В работе',
  done: 'Решение принято',
  cancelled: 'Снята',
}

export const label = (dictionary: Record<string, string>, code: string) => dictionary[code] ?? code
