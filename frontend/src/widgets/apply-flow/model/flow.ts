import { reactive } from 'vue'

import { loanDraft } from '@/entities/application'
import { customer } from '@/entities/customer'

/** Разделы кабинета клиента — модалки поверх лендинга */
export type CabinetSection = 'applications' | 'card' | 'notifications' | 'company' | 'profile'

type Modal = 'login' | 'application' | CabinetSection | null

/**
 * Какая модалка сайта открыта: вход, мастер заявки или раздел кабинета.
 * Все кнопки «Оформить» и пункты меню аккаунта ведут сюда, поэтому проверка «вошёл ли» — в одном месте.
 */
export const applyFlow = reactive<{
  modal: Modal
  continueToApplication: boolean
  checking: boolean
  /** Какая заявка открыта в модалке заявки */
  cardId: string | null
  /** Откуда открыли заявку — кнопка «Назад» вернёт туда */
  cardFrom: CabinetSection | null
}>({
  modal: null,
  continueToApplication: false,
  checking: false,
  cardId: null,
  cardFrom: null,
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

/** Раздел кабинета; заявку — по id. Не вошёл — сначала вход */
export function openCabinet(section: CabinetSection, applicationId?: string): void {
  if (!customer.state.token) {
    openLogin()
    return
  }
  if (section === 'card') {
    applyFlow.cardFrom = applyFlow.modal === 'card' ? applyFlow.cardFrom : isCabinet(applyFlow.modal) ? applyFlow.modal : null
    applyFlow.cardId = applicationId ?? applyFlow.cardId
  }
  applyFlow.modal = section
}

export function openApplicationCard(applicationId: string): void {
  openCabinet('card', applicationId)
}

/** «Назад» из заявки — в раздел, откуда её открыли */
export function backFromCard(): void {
  applyFlow.modal = applyFlow.cardFrom
  applyFlow.cardFrom = null
}

function isCabinet(modal: Modal): modal is CabinetSection {
  return modal === 'applications' || modal === 'notifications' || modal === 'company' || modal === 'profile' || modal === 'card'
}
