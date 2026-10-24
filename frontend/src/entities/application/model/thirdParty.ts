import type { BeneficialOwnersDto, BeneficiaryBasis, BeneficiaryDto, ThirdPartyDto } from '@/shared/api'

import { countryName } from './countries'

/** Основание действовать в интересах третьего лица — подписи для списка и карточки */
export const BENEFICIARY_BASIS_LABEL: Record<BeneficiaryBasis, string> = {
  agency: 'Агентский договор',
  mandate: 'Договор поручения',
  commission: 'Договор комиссии',
  trust_management: 'Доверительное управление',
}

/** «ООО «Принципал», ИНН 7707083893» или «Иванов Иван Иванович, Германия» */
export function thirdPartyLine(party: ThirdPartyDto): string {
  return [party.name, party.inn && `ИНН ${party.inn}`, countryName(party.country)].filter(Boolean).join(', ')
}

/** Ответ клиента одной строкой: «В интересах: …, агентский договор» или «В своих интересах» */
export function beneficiaryLine(answer: BeneficiaryDto): string {
  if (!answer.acts_for_third_party) return 'В своих интересах'
  const who = answer.beneficiary ? thirdPartyLine(answer.beneficiary) : 'не указано'
  const basis = answer.basis ? `, ${(BENEFICIARY_BASIS_LABEL[answer.basis] ?? answer.basis).toLowerCase()}` : ''
  return `В интересах: ${who}${basis}`
}

/** Чей залог: «заёмщик» или «третье лицо — Петров Пётр Петрович» */
export function collateralOwnerLine(collateral: { owner: string; owner_party?: ThirdPartyDto | null }): string {
  if (collateral.owner !== 'third_party') return 'заёмщик'
  return collateral.owner_party ? `третье лицо — ${thirdPartyLine(collateral.owner_party)}` : 'третье лицо, не указано'
}

export const OWNER_BASIS_LABEL: Record<string, string> = {
  ownership: 'владеет больше 25%',
  control: 'контролирует иначе',
}

/** Бенефициары со слов клиента одной строкой: «Никто» или «Смирнова А. С. (владеет больше 25%), Теневой Т. (контролирует иначе, ОАЭ)» */
export function beneficialOwnersLine(answer: Pick<BeneficialOwnersDto, 'owners'>): string {
  if (!answer.owners.length) return 'Никто не владеет больше 25% и не контролирует компанию иначе'
  return answer.owners
    .map((owner) => `${owner.name} (${[OWNER_BASIS_LABEL[owner.basis] ?? owner.basis, countryName(owner.country)].filter(Boolean).join(', ')})`)
    .join(', ')
}
