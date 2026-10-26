import { describe, expect, it } from 'vitest'

import { beneficialOwnersLine, beneficiaryLine, collateralOwnerLine, countryName, thirdPartyLine } from '@/entities/application'

import { emptyOwners, MAX_OWNERS, ownersProblems, toOwnersForm, toOwnersInput, type OwnersForm } from './owners'
import { emptyThirdParty, thirdPartyProblems, toBeneficiaryInput, toThirdPartyForm, toThirdPartyInput, type ThirdPartyForm } from './thirdParty'
import { describeViolations } from './violations'

/** Ответы по 115-ФЗ в мастере заявки: выгодоприобретатель, бенефициары, третьи лица (docs/compliance-115.md) */

const DECLARED_AT = '2026-10-26T09:00:00Z'

describe('бенефициары (ст. 6.1)', () => {
  it('клиент ещё не ответил — поле не отправляем', () => {
    expect(toOwnersInput(emptyOwners())).toBeUndefined()
  })

  it('«Никто» — пустой список', () => {
    expect(toOwnersInput({ answer: 'none', owners: [] })).toEqual({ owners: [] })
  })

  it('названные бенефициары: имя без лишних пробелов, Россия — без кода страны', () => {
    const form: OwnersForm = {
      answer: 'list',
      owners: [
        { name: '  Смирнова Анна Сергеевна ', basis: 'ownership', country: '' },
        { name: 'Теневой Т.', basis: 'control', country: 'AE' },
      ],
    }
    expect(toOwnersInput(form)).toEqual({
      owners: [
        { name: 'Смирнова Анна Сергеевна', basis: 'ownership', country: null },
        { name: 'Теневой Т.', basis: 'control', country: 'AE' },
      ],
    })
  })

  it('из сохранённого ответа форма восстанавливается', () => {
    expect(toOwnersForm(null).answer).toBeNull()
    expect(toOwnersForm({ owners: [], declared_at: DECLARED_AT }).answer).toBe('none')
    const restored = toOwnersForm({ owners: [{ name: 'Смирнова А. С.', basis: 'ownership', country: null }], declared_at: DECLARED_AT })
    expect(restored).toEqual({ answer: 'list', owners: [{ name: 'Смирнова А. С.', basis: 'ownership', country: '' }] })
  })

  it('ошибки — по тем же путям, что вернул бы бэкенд', () => {
    const form: OwnersForm = { answer: 'list', owners: [{ name: ' ', basis: 'ownership', country: 'de' }] }
    expect(ownersProblems(form)).toEqual({
      'beneficial_owners.owners.0.name': 'Укажите ФИО или наименование',
      'beneficial_owners.owners.0.country': 'Код страны — две латинские буквы',
    })
    expect(ownersProblems({ answer: 'none', owners: [] })).toEqual({})
  })

  it('бэкенд принимает до 20 бенефициаров', () => {
    expect(MAX_OWNERS).toBe(20)
  })

  it('строка для карточки: «Никто» или список с основаниями и страной', () => {
    expect(beneficialOwnersLine({ owners: [] })).toBe('Никто не владеет больше 25% и не контролирует компанию иначе')
    expect(
      beneficialOwnersLine({
        owners: [
          { name: 'Смирнова А. С.', basis: 'ownership', country: null },
          { name: 'Теневой Т.', basis: 'control', country: 'AE' },
        ],
      }),
    ).toBe('Смирнова А. С. (владеет больше 25%), Теневой Т. (контролирует иначе, ОАЭ)')
  })
})

describe('выгодоприобретатель и третьи лица', () => {
  const principal: ThirdPartyForm = { kind: 'organization', name: ' ООО «Принципал» ', inn: '7707083893', country: '' }

  it('в своих интересах — без третьего лица', () => {
    expect(toBeneficiaryInput({ acts: false, party: principal, basis: 'agency' })).toEqual({ acts_for_third_party: false })
  })

  it('в интересах третьего лица — кто и на каком основании', () => {
    expect(toBeneficiaryInput({ acts: true, party: principal, basis: 'agency' })).toEqual({
      acts_for_third_party: true,
      beneficiary: { kind: 'organization', name: 'ООО «Принципал»', inn: '7707083893', country: null },
      basis: 'agency',
    })
    expect(toBeneficiaryInput({ acts: true, party: principal, basis: '' })).toMatchObject({ basis: null })
  })

  it('пустой ИНН у физлица — null, а не пустая строка', () => {
    expect(toThirdPartyInput({ kind: 'person', name: 'Петров П. П.', inn: ' ', country: 'DE' })).toEqual({
      kind: 'person',
      name: 'Петров П. П.',
      inn: null,
      country: 'DE',
    })
  })

  it('проверка формы: организации нужен ИНН, ИНН — с верной контрольной суммой, страна — кодом', () => {
    expect(thirdPartyProblems(emptyThirdParty(), 'beneficiary.beneficiary')).toEqual({
      'beneficiary.beneficiary.name': 'Укажите наименование',
      'beneficiary.beneficiary.inn': 'Укажите ИНН',
    })
    expect(thirdPartyProblems({ kind: 'person', name: '', inn: '', country: '' }, 'collateral.owner_party')).toEqual({
      'collateral.owner_party.name': 'Укажите ФИО',
    })
    expect(thirdPartyProblems({ ...principal, inn: '7707083894', country: 'Germany' }, 'p')).toEqual({
      'p.inn': 'Проверьте ИНН — в нём ошибка',
      'p.country': 'Код страны — две латинские буквы',
    })
    expect(thirdPartyProblems(principal, 'p')).toEqual({})
  })

  it('форма восстанавливается из ответа', () => {
    expect(toThirdPartyForm(null)).toEqual(emptyThirdParty())
    expect(toThirdPartyForm({ kind: 'person', name: 'Петров П. П.', inn: null, country: 'DE' })).toEqual({
      kind: 'person',
      name: 'Петров П. П.',
      inn: '',
      country: 'DE',
    })
  })

  it('строки для карточки заявки', () => {
    expect(thirdPartyLine({ kind: 'organization', name: 'ООО «Принципал»', inn: '7707083893', country: null })).toBe(
      'ООО «Принципал», ИНН 7707083893',
    )
    expect(thirdPartyLine({ kind: 'person', name: 'Иванов Иван Иванович', inn: null, country: 'DE' })).toBe('Иванов Иван Иванович, Германия')
    expect(beneficiaryLine({ acts_for_third_party: false, beneficiary: null, basis: null, declared_at: DECLARED_AT })).toBe('В своих интересах')
    expect(
      beneficiaryLine({
        acts_for_third_party: true,
        beneficiary: { kind: 'organization', name: 'ООО «Принципал»', inn: '7707083893' },
        basis: 'agency',
        declared_at: DECLARED_AT,
      }),
    ).toBe('В интересах: ООО «Принципал», ИНН 7707083893, агентский договор')
    expect(collateralOwnerLine({ owner: 'self' })).toBe('заёмщик')
    expect(collateralOwnerLine({ owner: 'third_party', owner_party: null })).toBe('третье лицо, не указано')
  })

  it('страны «чёрного списка» ФАТФ названы по-русски, Россия — без кода', () => {
    expect(countryName('KP')).toBe('КНДР')
    expect(countryName('IR')).toBe('Иран')
    expect(countryName('MM')).toBe('Мьянма')
    expect(countryName(null)).toBeNull()
    expect(countryName('FR')).toBe('FR')
  })
})

describe('describeViolations — нарушения комплектности понятным текстом', () => {
  const context = { documentTitle: (type: string) => `документ ${type}`, fieldTitle: () => 'Стоимость объекта' }

  it('ведёт клиента на тот шаг мастера, где исправить', () => {
    const views = describeViolations(
      [
        { code: 'out_of_range', field: 'request.amount' },
        { code: 'missing', field: 'documents.bank_statement' },
        { code: 'missing', field: 'consents.credit_bureau' },
        { code: 'bad_checksum', field: 'beneficiary.beneficiary.inn' },
        { code: 'missing', field: 'beneficial_owners.owners.1.name' },
        { code: 'missing', field: 'product_fields.price' },
        { code: 'duplicate_active', field: 'product_code' },
      ],
      context,
    )
    expect(views).toEqual([
      { step: 'terms', message: 'Вне условий продукта: сумма кредита' },
      { step: 'details', message: 'Не загружен документ: документ bank_statement' },
      { step: 'consents', message: 'Не заполнено: согласие на запрос в бюро кредитных историй' },
      { step: 'consents', message: 'Неверный ИНН: ИНН того, в чьих интересах вы действуете' },
      { step: 'consents', message: 'Не заполнено: ФИО бенефициара № 2' },
      { step: 'details', message: 'Не заполнено: «Стоимость объекта»' },
      { step: 'terms', message: 'По этому продукту у компании уже есть заявка в работе — дождитесь решения по ней' },
    ])
  })

  it('незнакомое поле показывает как есть', () => {
    expect(describeViolations([{ code: 'invalid', field: 'something.else' }], context)).toEqual([
      { step: 'details', message: 'Проверьте: something.else' },
    ])
  })
})
