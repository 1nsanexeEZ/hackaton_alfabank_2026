import type { BeneficiaryBasis, BeneficiaryInput, ThirdPartyDto, ThirdPartyInput } from '@/shared/api'
import { isValidInn } from '@/shared/lib'

/** Третье лицо в форме: выгодоприобретатель или владелец залога */
export interface ThirdPartyForm {
  kind: 'organization' | 'person'
  name: string
  inn: string
}

/** Ответ на вопрос о третьем лице; acts = null — клиент ещё не ответил */
export interface BeneficiaryForm {
  acts: boolean | null
  party: ThirdPartyForm
  basis: BeneficiaryBasis | ''
}

export const emptyThirdParty = (): ThirdPartyForm => ({ kind: 'organization', name: '', inn: '' })

export function toThirdPartyForm(party: ThirdPartyDto | null | undefined): ThirdPartyForm {
  if (!party) return emptyThirdParty()
  return { kind: party.kind === 'person' ? 'person' : 'organization', name: party.name, inn: party.inn ?? '' }
}

export function toThirdPartyInput(party: ThirdPartyForm): ThirdPartyInput {
  const inn = party.inn.trim()
  return { kind: party.kind, name: party.name.trim(), inn: inn || null }
}

export function toBeneficiaryInput(form: BeneficiaryForm): BeneficiaryInput {
  if (!form.acts) return { acts_for_third_party: false }
  return { acts_for_third_party: true, beneficiary: toThirdPartyInput(form.party), basis: form.basis || null }
}

/** Ошибки полей третьего лица по пути prefix.name / prefix.inn — как их вернул бы бэкенд */
export function thirdPartyProblems(party: ThirdPartyForm, prefix: string): Record<string, string> {
  const errors: Record<string, string> = {}
  const inn = party.inn.trim()
  if (!party.name.trim()) {
    errors[`${prefix}.name`] = party.kind === 'organization' ? 'Укажите наименование' : 'Укажите ФИО'
  }
  if (party.kind === 'organization' && !inn) errors[`${prefix}.inn`] = 'Укажите ИНН'
  else if (inn && !isValidInn(inn)) errors[`${prefix}.inn`] = 'Проверьте ИНН — в нём ошибка'
  return errors
}
