import rawSources from '../../../../mocks/external-sources.json'

/**
 * Ответы внешних источников по ИНН: ЕГРЮЛ/ЕГРИП, ФНС «Прозрачный бизнес», ГИР БО, Контур.
 * Структура совпадает с frontend/mocks/external-sources.json — тем же файлом может пользоваться мок бэкенда.
 */
export type ExpectedOutcome = 'approved' | 'counter_offer' | 'info_requested' | 'rejected'

export interface Okved {
  main: { code: string; name: string }
  additional: { code: string; name: string }[]
}

export interface EgrulRecord {
  inn: string
  kpp: string
  ogrn: string
  opf: string
  name_full: string
  name_short: string
  status: string
  status_date: string | null
  registration_date: string
  registration_authority: string
  address: { region_code: string; full: string; unreliable: boolean }
  authorized_capital_rub: number
  director: { position: string; name: string; inn: string; since: string; unreliable: boolean }
  founders: { name: string; inn: string; share_percent: number; share_rub: number }[]
  okved: Okved
  last_update: string
}

export interface EgripRecord {
  inn: string
  ogrnip: string
  fio: string
  citizenship: string
  status: string
  status_date: string | null
  registration_date: string
  registration_authority: string
  region_code: string
  okved: Okved
  last_update: string
}

export interface FnsRecord {
  tax_regime: string
  average_headcount: number
  msp_register: { included: boolean; category: string | null }
  taxes_paid: { year: number; paid_rub: number }[]
  tax_arrears_rub: number
  account_blocks: { decision_number: string; date: string; authority_code: string; reason: string }[]
  mass_registration_address: boolean
  disqualified_persons: boolean
  unreliable_data: string[]
  checked_at: string
}

/** Строки форм бухотчётности, тыс. ₽ */
export interface GirBoPeriod {
  year: number
  balance: {
    '1150_fixed_assets': number
    '1210_inventories': number
    '1230_receivables': number
    '1250_cash': number
    '1600_total_assets': number
    '1300_equity': number
    '1400_long_term_liabilities': number
    '1500_short_term_liabilities': number
    '1700_total_liabilities': number
  }
  income: {
    '2110_revenue': number
    '2120_cost_of_sales': number
    '2200_sales_profit': number
    '2330_interest_payable': number
    '2300_profit_before_tax': number
    '2400_net_profit': number
  }
}

export interface GirBoRecord {
  available: boolean
  reason?: string
  periods: GirBoPeriod[]
}

export type Reliability = 'green' | 'yellow' | 'red'

export interface KonturRecord {
  reliability: Reliability
  reliability_notes: string[]
  arbitration: { as_defendant: number; as_plaintiff: number; defendant_sum_rub: number }
  enforcement_proceedings: { active: number; sum_rub: number }
  gov_contracts: { count: number; sum_rub: number }
  bankruptcy_messages: { date: string; type: string; case: string }[]
  active_pledges: number
  affiliated_companies: number
  checked_at: string
}

interface DossierBase {
  scenario: string
  expected_outcome: ExpectedOutcome
  fns: FnsRecord
  gir_bo: GirBoRecord
  kontur: KonturRecord
}

export interface CompanyDossier extends DossierBase {
  kind: 'company'
  egrul: EgrulRecord
}

export interface EntrepreneurDossier extends DossierBase {
  kind: 'entrepreneur'
  egrip: EgripRecord
}

export type Dossier = CompanyDossier | EntrepreneurDossier

interface SourcesFile {
  companies: Omit<CompanyDossier, 'kind'>[]
  entrepreneurs: Omit<EntrepreneurDossier, 'kind'>[]
}

const sources = rawSources as unknown as SourcesFile

export const DOSSIERS: readonly Dossier[] = [
  ...sources.companies.map((item): CompanyDossier => ({ kind: 'company', ...item })),
  ...sources.entrepreneurs.map((item): EntrepreneurDossier => ({ kind: 'entrepreneur', ...item })),
]

export function dossierInn(dossier: Dossier): string {
  return dossier.kind === 'company' ? dossier.egrul.inn : dossier.egrip.inn
}

/** Название для списков: «ООО «Ромашка»» или «ИП Иванов И. И.» */
export function dossierName(dossier: Dossier): string {
  if (dossier.kind === 'company') return dossier.egrul.name_short
  const [last, first = '', middle = ''] = dossier.egrip.fio.split(' ')
  return `ИП ${last} ${first.charAt(0)}.${middle ? ` ${middle.charAt(0)}.` : ''}`
}

export function dossierStatus(dossier: Dossier): string {
  return dossier.kind === 'company' ? dossier.egrul.status : dossier.egrip.status
}

export function dossierRegistrationDate(dossier: Dossier): string {
  return dossier.kind === 'company' ? dossier.egrul.registration_date : dossier.egrip.registration_date
}

export function findDossier(inn: string): Dossier | null {
  return DOSSIERS.find((item) => dossierInn(item) === inn) ?? null
}
