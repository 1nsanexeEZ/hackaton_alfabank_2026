import { reactive } from 'vue'

import type { ApplicationDraft } from './types'

/**
 * Параметры кредита, которые клиент выбрал на сайте: продукт, сумма, срок.
 * Общие для каталога, калькулятора и модалки заявки — кнопка «Оформить» в шапке
 * открывает заявку с тем, что клиент уже посчитал. productId пуст, пока не загрузился каталог.
 */
export const loanDraft = reactive<ApplicationDraft>({ productId: '', amount: 0, termMonths: 0 })
