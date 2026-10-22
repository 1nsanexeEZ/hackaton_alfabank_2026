import { reactive } from 'vue'

import { loanDraft } from '@/entities/application'
import { customer } from '@/entities/customer'

type Modal = 'login' | 'application' | null

/**
 * Какая модалка открыта: вход или заявка. Все кнопки «Оформить» на сайте ведут сюда,
 * поэтому проверка «вошёл ли пользователь» — в одном месте.
 */
export const applyFlow = reactive<{ modal: Modal; continueToApplication: boolean; checking: boolean }>({
  modal: null,
  continueToApplication: false,
  checking: false,
})

/**
 * Оформить заявку: вошёл — сразу модалка заявки; нет — сначала модалка входа, после него — заявка.
 * Вход проверяем по живому токену через GET /me: истёкший токен — это «не вошёл».
 */
export async function startApplication(productId?: string): Promise<void> {
  if (productId) loanDraft.productId = productId
  applyFlow.checking = true
  try {
    const me = await customer.restore()
    applyFlow.continueToApplication = !me
    applyFlow.modal = me ? 'application' : 'login'
  } finally {
    applyFlow.checking = false
  }
}

/** Просто войти, без заявки — кнопка «Войти» в шапке */
export function openLogin(): void {
  applyFlow.continueToApplication = false
  applyFlow.modal = 'login'
}

export function onLoggedIn(): void {
  applyFlow.modal = applyFlow.continueToApplication ? 'application' : null
  applyFlow.continueToApplication = false
}

/** В модалке заявки выяснилось, что у учётки нет компаний: выходим и предлагаем войти другой */
export function switchAccount(): void {
  customer.logout()
  applyFlow.continueToApplication = true
  applyFlow.modal = 'login'
}
