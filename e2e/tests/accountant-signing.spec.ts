import { expect, test } from '@playwright/test'

import { ROMASHKA_ACCOUNTANT, ROMASHKA_OWNER } from '../support/accounts'
import { closeActiveApplications } from '../support/api'
import { signContract } from '../support/contract'
import { applicationWizard, choose, signIn } from '../support/ui'
import { fillTerms, openSubmittedFromHero, submitWithConsents } from '../support/wizard'

/**
 * S-8 из README: права внутри компании. Бухгалтер подаёт заявку и принимает предложение,
 * но подписать договор без доверенности на подпись не может — подписывает директор.
 */
test.describe('S-8: бухгалтер подаёт, подписывает директор', () => {
  test.beforeEach(async ({ request }) => {
    await closeActiveApplications(request, ROMASHKA_OWNER, 'UNSECURED')
  })

  test('бухгалтер «Ромашки» доводит заявку до подписи, договор подписывает директор', async ({ page, browser }) => {
    const wizard = applicationWizard(page)
    const card = page.getByRole('dialog', { name: /Кредит без залога/ })
    let number = ''

    await test.step('Бухгалтер двух компаний выбирает «Ромашку» и подаёт заявку', async () => {
      await signIn(page, ROMASHKA_ACCOUNTANT)
      await page.goto('/')
      await page.getByRole('main').getByRole('button', { name: 'Оформить заявку' }).first().click()
      // Участник нескольких компаний сначала выбирает, от какой заявка
      await expect(wizard.getByRole('contentinfo')).toContainText('Компания')
      await choose(page, wizard, 'Компания', 'ООО «Ромашка» · ИНН 7701158817')
      await fillTerms(page, {
        purpose: 'Пополнение оборотных средств',
        product: 'Кредит без залога',
        amount: 3_000_000,
        termMonths: 24,
        termLabel: '2 года',
      })
      await wizard.getByRole('button', { name: 'Далее' }).click()
      number = await submitWithConsents(page, 'Смирнова Анна Сергеевна')
    })

    await test.step('Бухгалтер принимает одобрение, но подписать не может', async () => {
      await openSubmittedFromHero(page, number)
      await expect(card.getByText('Банк одобрил заявку на запрошенных условиях')).toBeVisible({ timeout: 90_000 })
      await card.getByRole('button', { name: 'Принять предложение' }).click()
      await expect(card.getByText('Договор ждёт подписи')).toBeVisible({ timeout: 60_000 })
      await expect(card.getByText('Подписать может руководитель компании или сотрудник с доверенностью на подпись.')).toBeVisible()
      await expect(card.getByRole('button', { name: 'Подписать договор' })).toHaveCount(0)
    })

    const director = await browser.newPage()
    const directorCard = director.getByRole('dialog', { name: /Кредит без залога/ })

    await test.step('Директор открывает ту же заявку и подписывает договор', async () => {
      await signIn(director, ROMASHKA_OWNER)
      await director.goto('/')
      const hero = director.getByRole('article', { name: `Ваша заявка № ${number}` })
      await hero.getByRole('button', { name: 'Подробнее о заявке' }).click()
      await expect(directorCard.getByText('Подпишите договор')).toBeVisible()
      await signContract(director, directorCard, number)
    })

    await test.step('Бухгалтер видит выдачу в своей карточке', async () => {
      await expect(card.getByText('Договор подписан сторонами, кредит выдан')).toBeVisible({ timeout: 60_000 })
    })

    await director.close()
  })
})
