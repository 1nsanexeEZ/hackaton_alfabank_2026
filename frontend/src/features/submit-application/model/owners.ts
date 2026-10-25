import type { BeneficialOwnerInput, BeneficialOwnersDto } from '@/shared/api'

/** Бенефициар в форме; country — код страны, пусто — Россия */
export interface OwnerForm {
  name: string
  basis: BeneficialOwnerInput['basis']
  country: string
}

/**
 * Ответ о бенефициарах (115-ФЗ ст. 6.1): none — больше 25% ни у кого и никто не контролирует компанию
 * иначе, list — названные люди, null — клиент ещё не ответил (дальше шага согласий форма не пустит)
 */
export interface OwnersForm {
  answer: 'none' | 'list' | null
  owners: OwnerForm[]
}

/** Сколько бенефициаров принимает бэкенд */
export const MAX_OWNERS = 20

export const emptyOwner = (): OwnerForm => ({ name: '', basis: 'ownership', country: '' })
export const emptyOwners = (): OwnersForm => ({ answer: null, owners: [emptyOwner()] })

export function toOwnersForm(answer: BeneficialOwnersDto | null | undefined): OwnersForm {
  if (!answer) return emptyOwners()
  if (!answer.owners.length) return { answer: 'none', owners: [emptyOwner()] }
  return {
    answer: 'list',
    owners: answer.owners.map((owner) => ({ name: owner.name, basis: owner.basis, country: owner.country ?? '' })),
  }
}

/** Что отправить в PATCH; undefined — клиент не ответил, поле не передаём */
export function toOwnersInput(form: OwnersForm): { owners: BeneficialOwnerInput[] } | undefined {
  if (form.answer === null) return undefined
  if (form.answer === 'none') return { owners: [] }
  return {
    owners: form.owners.map((owner) => ({ name: owner.name.trim(), basis: owner.basis, country: owner.country || null })),
  }
}

/** Ошибки по путям beneficial_owners.owners.N.name / .country — как их вернул бы бэкенд */
export function ownersProblems(form: OwnersForm): Record<string, string> {
  const errors: Record<string, string> = {}
  if (form.answer !== 'list') return errors
  form.owners.forEach((owner, index) => {
    if (!owner.name.trim()) errors[`beneficial_owners.owners.${index}.name`] = 'Укажите ФИО или наименование'
    if (owner.country && !/^[A-Z]{2}$/.test(owner.country)) errors[`beneficial_owners.owners.${index}.country`] = 'Код страны — две латинские буквы'
  })
  return errors
}
