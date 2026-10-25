import { expect, type Page } from '@playwright/test'

import { applicationWizard, choose, money } from './ui'

export interface LoanTerms {
  purpose: string
  product: string
  amount: number
  termMonths: number
  /** Как срок пишет сайт: «2 года», «1 год» */
  termLabel: string
}

/** Шаг «Условия»: цель, продукт, сумма и срок — ползунками, как двигает их клиент */
export async function fillTerms(page: Page, terms: LoanTerms): Promise<void> {
  const wizard = applicationWizard(page)
  await choose(page, wizard, 'Для чего нужны деньги', terms.purpose)
  await choose(page, wizard, 'Продукт', terms.product)
  await wizard.getByRole('slider', { name: 'Сумма кредита' }).fill(String(terms.amount))
  await expect(wizard.getByRole('textbox', { name: 'Сумма кредита' })).toHaveValue(money(terms.amount))
  await wizard.getByRole('slider', { name: 'Срок' }).fill(String(terms.termMonths))
  await expect(wizard.getByRole('textbox', { name: 'Срок' })).toHaveValue(terms.termLabel)
}

/**
 * Шаг «Согласия и отправка»: кредит в своих интересах, бенефициар — как в ЕГРЮЛ, согласия на ПДн и БКИ.
 * Бенефициара называем по реестру: ответ «Никто» банк сверит с ЕГРЮЛ, увидит расхождение
 * и по 115-ФЗ отправит заявку специалисту, а не решит её автоматически.
 * Возвращает номер отправленной заявки.
 */
export async function submitWithConsents(page: Page, beneficialOwner: string): Promise<string> {
  const wizard = applicationWizard(page)
  await expect(wizard).toContainText('Согласия и отправка')
  await wizard.getByRole('radio', { name: 'Нет, в своих интересах' }).click()
  await wizard.getByRole('radio', { name: 'Есть такие — назову' }).click()
  await wizard.getByRole('textbox', { name: 'ФИО или наименование' }).fill(beneficialOwner)
  await expect(wizard.getByRole('button', { name: 'Владеет больше 25%' })).toHaveAttribute('aria-pressed', 'true')
  // Согласия могли прийти из профиля уже отмеченными — check() их не снимет
  await wizard.getByRole('checkbox', { name: 'Согласен на обработку персональных данных' }).check()
  await wizard.getByRole('checkbox', { name: /запрос кредитной истории компании/ }).check()
  await wizard.getByRole('button', { name: 'Отправить заявку' }).click()

  const submitted = wizard.getByRole('heading', { name: /Заявка № \S+ отправлена/ })
  await expect(submitted).toBeVisible()
  const number = /№ (\S+)/.exec((await submitted.textContent()) ?? '')?.[1]
  if (!number) throw new Error('Мастер не показал номер отправленной заявки')
  return number
}

/** «Готово» в мастере → карточка заявки на первом экране → «Подробнее о заявке» */
export async function openSubmittedFromHero(page: Page, number: string): Promise<void> {
  await applicationWizard(page).getByRole('button', { name: 'Готово' }).click()
  const hero = page.getByRole('article', { name: `Ваша заявка № ${number}` })
  await expect(hero).toBeVisible()
  await hero.getByRole('button', { name: 'Подробнее о заявке' }).click()
}
