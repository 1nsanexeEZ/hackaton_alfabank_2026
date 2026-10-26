import type { FinancialReportDto, FinancialReportInput } from '@/shared/api'

/** Отчёт в форме — как его ввёл клиент: суммы строками («3 000 000»), убыток со знаком минус, квартал пустой — год целиком */
export interface ReportForm {
  year: string
  quarter: '' | '1' | '2' | '3' | '4'
  revenue: string
  expenses: string
  netProfit: string
  liabilities: string
  debtPayments: string
}

export type ReportFormErrors = Partial<Record<keyof ReportForm, string>>

const toNumber = (value: string) => Number(value.replace(/\s/g, '').replace(',', '.'))
const optional = (value: string) => (value.trim() ? toNumber(value) : null)

/** «2 кв. 2025» или «2025 год» */
export function reportPeriod(report: Pick<FinancialReportDto, 'period_year' | 'period_quarter'>): string {
  return report.period_quarter ? `${report.period_quarter} кв. ${report.period_year}` : `${report.period_year} год`
}

/** Ошибки полей формы; пусто — можно отправлять. Отчёт за будущий год не принимаем */
export function reportFormErrors(form: ReportForm, currentYear = new Date().getFullYear()): ReportFormErrors {
  const errors: ReportFormErrors = {}
  const year = Number(form.year)
  if (!Number.isInteger(year) || year < 2000 || year > currentYear) errors.year = 'Укажите год'
  if (!(toNumber(form.revenue) >= 0) || !form.revenue.trim()) errors.revenue = 'Укажите выручку'
  for (const key of ['expenses', 'netProfit', 'liabilities', 'debtPayments'] as const) {
    if (form[key].trim() && !Number.isFinite(toNumber(form[key]))) errors[key] = 'Введите число'
  }
  // Прибыль — из выручки: больше неё не бывает; убыток — со знаком минус
  if (!errors.netProfit && form.netProfit.trim() && !errors.revenue && toNumber(form.netProfit) > toNumber(form.revenue)) {
    errors.netProfit = 'Не больше выручки'
  }
  return errors
}

/** Что отправить банку: пустые необязательные поля — null */
export function toReportInput(form: ReportForm): FinancialReportInput {
  return {
    period_year: Number(form.year),
    period_quarter: form.quarter ? Number(form.quarter) : null,
    revenue: toNumber(form.revenue),
    expenses: optional(form.expenses),
    net_profit: optional(form.netProfit),
    total_liabilities: optional(form.liabilities),
    monthly_debt_payments: optional(form.debtPayments),
  }
}
