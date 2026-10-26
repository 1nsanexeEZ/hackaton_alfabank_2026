import { expect, test } from '@playwright/test'

import { ZAKAT_OWNER } from '../support/accounts'
import { closeActiveApplications } from '../support/api'
import { applicationWizard, signIn } from '../support/ui'
import { fillTerms, openSubmittedFromHero, submitWithConsents } from '../support/wizard'

/**
 * S-4 из README: компания в стадии ликвидации с просрочкой больше 90 дней получает отказ
 * по стоп-факторам до скоринга, и клиент видит понятную причину и что поможет в следующий раз.
 */
test.describe('S-4: отказ по стоп-факторам', () => {
  test.beforeEach(async ({ request }) => {
    await closeActiveApplications(request, ZAKAT_OWNER, 'UNSECURED')
  })

  test('директор «Заката» видит отказ с объяснением', async ({ page }) => {
    await signIn(page, ZAKAT_OWNER)
    await page.goto('/')
    await page.getByRole('main').getByRole('button', { name: 'Оформить заявку' }).first().click()

    const wizard = applicationWizard(page)
    await expect(wizard).toContainText('ООО «Закат»')
    await fillTerms(page, {
      purpose: 'Пополнение оборотных средств',
      product: 'Кредит без залога',
      amount: 2_000_000,
      termMonths: 12,
      termLabel: '1 год',
    })
    await wizard.getByRole('button', { name: 'Далее' }).click()
    const number = await submitWithConsents(page, 'Закатов Олег Олегович')

    await openSubmittedFromHero(page, number)
    const card = page.getByRole('dialog', { name: /Кредит без залога/ })
    await expect(card.getByText('Банк не может выдать кредит')).toBeVisible({ timeout: 90_000 })
    // Подсказки — по стоп-факторам компании: недоимка, просрочка перед кредиторами
    const hints = card.getByText('Что поможет в следующий раз', { exact: true }).locator('xpath=following-sibling::ul')
    await expect(hints.getByRole('listitem').first()).toBeVisible()
    await expect(hints).toContainText('задолженност')
    // Отказ — итог: ни предложения, ни отмены, остаётся только вопрос поддержке
    await expect(card.getByRole('button', { name: 'Принять предложение' })).toHaveCount(0)
    await expect(card.getByRole('button', { name: 'Отменить заявку' })).toHaveCount(0)
    await expect(card.getByRole('button', { name: 'Вопрос поддержке' })).toBeVisible()
  })
})
