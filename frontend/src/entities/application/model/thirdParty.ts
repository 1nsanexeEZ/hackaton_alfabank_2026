import type { BeneficiaryBasis, BeneficiaryDto, ThirdPartyDto } from '@/shared/api'

/** Основание действовать в интересах третьего лица — подписи для списка и карточки */
export const BENEFICIARY_BASIS_LABEL: Record<BeneficiaryBasis, string> = {
  agency: 'Агентский договор',
  mandate: 'Договор поручения',
  commission: 'Договор комиссии',
  trust_management: 'Доверительное управление',
}

/** «ООО «Принципал», ИНН 7707083893» или «Иванов Иван Иванович» */
export function thirdPartyLine(party: ThirdPartyDto): string {
  return party.inn ? `${party.name}, ИНН ${party.inn}` : party.name
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
