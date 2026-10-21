import { dossierStatus, type Dossier } from '@/shared/api'
import { formatMoneyShort } from '@/shared/lib'

export type CheckLevel = 'ok' | 'warn' | 'fail'

export interface SourceCheck {
  source: string
  level: CheckLevel
  summary: string
}

const ACTIVE = ['Действующее', 'Действующий']

/** Короткий итог по каждому источнику — первая строка досье, которую видит аналитик */
export function summarizeChecks(dossier: Dossier): SourceCheck[] {
  const status = dossierStatus(dossier)
  const registry: SourceCheck = {
    source: dossier.kind === 'company' ? 'ЕГРЮЛ' : 'ЕГРИП',
    level: ACTIVE.includes(status) ? 'ok' : 'fail',
    summary: status,
  }

  const { fns } = dossier
  const fnsProblems = [
    fns.account_blocks.length && 'блокировка счёта',
    fns.tax_arrears_rub && `недоимка ${formatMoneyShort(fns.tax_arrears_rub)}`,
    fns.mass_registration_address && 'массовый адрес',
    fns.unreliable_data.length && 'недостоверные сведения',
    fns.disqualified_persons && 'дисквалификация',
  ].filter((item): item is string => Boolean(item))
  const tax: SourceCheck = {
    source: 'ФНС',
    level: fns.account_blocks.length ? 'fail' : fnsProblems.length ? 'warn' : 'ok',
    summary: fnsProblems.length ? fnsProblems.join(', ') : 'нарушений нет',
  }

  const lastPeriod = [...dossier.gir_bo.periods].sort((a, b) => b.year - a.year)[0]
  const reports: SourceCheck = {
    source: 'ГИР БО',
    level: !lastPeriod
      ? dossier.kind === 'company'
        ? 'warn'
        : 'ok'
      : lastPeriod.income['2400_net_profit'] < 0 || lastPeriod.balance['1300_equity'] < 0
        ? 'warn'
        : 'ok',
    summary: !lastPeriod
      ? dossier.kind === 'company'
        ? 'отчётности нет'
        : 'ИП не сдают'
      : `выручка ${formatMoneyShort(lastPeriod.income['2110_revenue'] * 1000)} за ${lastPeriod.year}`,
  }

  const { kontur } = dossier
  const reputation: SourceCheck = {
    source: 'Контур',
    level: { green: 'ok', yellow: 'warn', red: 'fail' }[kontur.reliability] as CheckLevel,
    summary: kontur.reliability_notes[0] ?? 'признаков риска нет',
  }

  return [registry, tax, reports, reputation]
}
