import { expect, test } from '@playwright/test'

import { PROGRESS_OWNER, UNDERWRITER } from '../support/accounts'
import { closeActiveApplications } from '../support/api'
import { decideTask, openFromQueue, signInStaff } from '../support/staff'
import { applicationWizard, signIn } from '../support/ui'
import {
  answerInfoRequest,
  fillTerms,
  openSubmittedFromHero,
  pdf,
  startApplication,
  statement,
  submitWithConsents,
  uploadDocument,
} from '../support/wizard'

/**
 * S-5 из README: банк сам просит выписку за 6 месяцев, клиент загружает её в карточке заявки и отвечает.
 * Выписка не подтверждает заявленную выручку — заявка у андеррайтера, он отказывает с комментарием.
 */
test.describe('S-5: запрос информации, затем ручное рассмотрение', () => {
  test.beforeEach(async ({ request }) => {
    await closeActiveApplications(request, PROGRESS_OWNER, 'CREDIT_LINE')
  })

  test('«Прогресс» отвечает на запрос выписки, андеррайтер видит расхождение с выручкой и отказывает', async ({ page, browser }) => {
    const wizard = applicationWizard(page)
    const card = page.getByRole('dialog', { name: /Кредитная линия/ })
    let number = ''

    await test.step('Клиент подаёт кредитную линию на 8 млн ₽ с отчётностью', async () => {
      await signIn(page, PROGRESS_OWNER)
      await startApplication(page, 'ООО «Прогресс»')
      await fillTerms(page, {
        purpose: 'Пополнение оборотных средств',
        product: 'Кредитная линия',
        amount: 8_000_000,
        termMonths: 24,
        termLabel: '2 года',
      })
      await wizard.getByRole('button', { name: 'Далее' }).click()
      await uploadDocument(page, 'Бухгалтерская отчётность', pdf('report-2025.pdf'))
      await wizard.getByRole('button', { name: 'Далее' }).click()
      number = await submitWithConsents(page, 'Прогрессов Павел Павлович')
      await openSubmittedFromHero(page, number)
    })

    await test.step('Банк сам запрашивает выписку — клиент загружает CSV и отвечает', async () => {
      await expect(card.getByText('Банку нужны данные').first()).toBeVisible({ timeout: 90_000 })
      await expect(card.getByRole('list', { name: 'Этапы заявки' })).toContainText('нужны данные')
      // Ответить, пока документ не загружен, нельзя
      await expect(card.getByRole('button', { name: 'Отправить ответ банку' })).toBeDisabled()
      await answerInfoRequest(page, card, [{ title: 'Выписка по расчётному счёту', file: statement('progress') }])
      await expect(card.getByText('Заявку смотрит специалист банка')).toBeVisible({ timeout: 90_000 })
    })

    const staff = await browser.newPage()

    await test.step('Андеррайтер видит, что выписка не подтвердила выручку, и отказывает', async () => {
      await signInStaff(staff, UNDERWRITER)
      await openFromQueue(staff, number)
      await expect(staff.getByText('Выписка не подтвердила заявленную выручку').first()).toBeVisible()
      await decideTask(staff, {
        decision: 'Отказать',
        comment: 'Обороты по выписке втрое ниже заявленной выручки',
      })
      // Решение и комментарий остаются в маршруте заявки
      await expect(staff.getByText('Комментарий андеррайтера: «Обороты по выписке втрое ниже заявленной выручки»')).toBeVisible()
    })

    await test.step('Клиент видит отказ, предложения нет', async () => {
      await expect(card.getByText('Банк не может выдать кредит')).toBeVisible({ timeout: 60_000 })
      await expect(card.getByRole('button', { name: 'Принять предложение' })).toHaveCount(0)
    })

    await staff.close()
  })
})
