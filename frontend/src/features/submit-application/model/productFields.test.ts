import { describe, expect, it } from 'vitest'

import type { FieldsSchema } from '@/shared/api'

import { fieldTitle, newRow, toFormValues, toPayload, validateFieldValues } from './productFields'

/** Анкета ипотеки (S-7): объект и его стоимость; рефинансирование — список кредитов */
const mortgage: FieldsSchema = {
  type: 'object',
  properties: {
    object_type: { type: 'string', title: 'Тип объекта', enum: ['office', 'warehouse'] },
    object_value: { type: 'number', title: 'Стоимость объекта, ₽', minimum: 1_000_000 },
    address: { type: 'string', title: 'Адрес', minLength: 10 },
  },
  required: ['object_type', 'object_value'],
}

const refinance: FieldsSchema = {
  type: 'object',
  properties: {
    loans: {
      type: 'array',
      title: 'Кредиты',
      minItems: 1,
      items: {
        type: 'object',
        properties: {
          creditor: { type: 'string', title: 'Банк-кредитор' },
          rate: { type: 'number', title: 'Ставка, %', maximum: 100 },
        },
        required: ['creditor'],
      },
    },
  },
  required: ['loans'],
}

describe('доп. поля заявки по JSON Schema продукта', () => {
  it('пустая форма: перечисление — первым значением, список — с одной строкой', () => {
    expect(toFormValues(mortgage)).toEqual({ object_type: 'office', object_value: '', address: '' })
    expect(toFormValues(refinance)).toEqual({ loans: [{ creditor: '', rate: '' }] })
  })

  it('из черновика значения становятся строками', () => {
    expect(toFormValues(mortgage, { object_value: 50_000_000, object_type: 'warehouse' })).toMatchObject({
      object_type: 'warehouse',
      object_value: '50000000',
    })
    expect(toFormValues(refinance, { loans: [{ creditor: 'Банк', rate: 18.5 }] })).toEqual({ loans: [{ creditor: 'Банк', rate: '18.5' }] })
  })

  it('проверка: обязательные, числа, пределы и длина — по путям нарушений бэкенда', () => {
    expect(validateFieldValues(mortgage, { object_type: 'office', object_value: '', address: 'коротко' })).toEqual({
      'product_fields.object_value': 'Заполните поле',
      'product_fields.address': 'Не короче 10 символов',
    })
    expect(validateFieldValues(mortgage, { object_type: 'office', object_value: '500 000', address: '' })).toEqual({
      'product_fields.object_value': 'Не меньше 1000000',
    })
    expect(validateFieldValues(mortgage, { object_type: 'office', object_value: 'дорого', address: '' })).toEqual({
      'product_fields.object_value': 'Введите число',
    })
    expect(validateFieldValues(refinance, { loans: [{ creditor: '', rate: '120' }] })).toEqual({
      'product_fields.loans.0.creditor': 'Заполните поле',
      'product_fields.loans.0.rate': 'Не больше 100',
    })
    expect(validateFieldValues(refinance, { loans: [] })).toEqual({ 'product_fields.loans': 'Добавьте хотя бы одну запись' })
  })

  it('в API — числа, пустое — null', () => {
    expect(toPayload(mortgage, { object_type: 'office', object_value: '50 000 000', address: ' ' })).toEqual({
      object_type: 'office',
      object_value: 50_000_000,
      address: null,
    })
    expect(toPayload(refinance, { loans: [{ creditor: 'Банк', rate: '18,5' }] })).toEqual({ loans: [{ creditor: 'Банк', rate: 18.5 }] })
  })

  it('название поля по пути нарушения', () => {
    expect(fieldTitle(refinance, 'product_fields.loans.0.rate')).toBe('Ставка, %')
    expect(fieldTitle(mortgage, 'product_fields.object_value')).toBe('Стоимость объекта, ₽')
    expect(fieldTitle(mortgage, 'product_fields.unknown')).toBe('Анкета продукта')
  })

  it('новая строка списка — пустая', () => {
    expect(newRow(refinance.properties!.loans!.items!)).toEqual({ creditor: '', rate: '' })
  })
})
