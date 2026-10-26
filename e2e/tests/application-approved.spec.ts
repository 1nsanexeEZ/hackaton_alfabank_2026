import { readFileSync, writeFileSync } from 'node:fs'

import { expect, test } from '@playwright/test'

import { DEMO_PASSWORD, ROMASHKA_OWNER } from '../support/accounts'
import { closeActiveApplications } from '../support/api'
import { applicationWizard, loginDrawer, money, signInWithDemo } from '../support/ui'
import { fillTerms, openSubmittedFromHero, submitWithConsents } from '../support/wizard'

/**
 * S-1 из README: благополучный заёмщик получает автоматическое одобрение, принимает предложение,
 * подписывает договор паролем, банк ставит свою подпись и выдаёт кредит; договор проверяется по QR.
 */
test.describe('S-1: одобрение, договор и подпись', () => {
  test.beforeEach(async ({ request }) => {
    await closeActiveApplications(request, ROMASHKA_OWNER, 'UNSECURED')
  })

  test('директор «Ромашки» получает кредит без залога от заявки до проверки договора', async ({ page }, testInfo) => {
    const wizard = applicationWizard(page)

    await test.step('«Оформить заявку» гостем ведёт на вход, после входа открывается мастер', async () => {
      await page.goto('/')
      await page.getByRole('main').getByRole('button', { name: 'Оформить заявку' }).first().click()
      await expect(loginDrawer(page)).toContainText('Чтобы оформить заявку, войдите')
      await signInWithDemo(page, ROMASHKA_OWNER)
      await expect(wizard).toBeVisible()
    })

    await test.step('Условия: реквизиты из базы банка, цель, продукт, сумма и срок', async () => {
      await expect(wizard).toContainText('ООО «Ромашка»')
      await expect(wizard).toContainText(/Из базы банка: ОГРН \d+/)
      await fillTerms(page, {
        purpose: 'Пополнение оборотных средств',
        product: 'Кредит без залога',
        amount: 3_000_000,
        termMonths: 24,
        termLabel: '2 года',
      })
      // Вошедшему — до какой суммы банк готов дать этой компании: предодобрение или посильное по отчётности
      await expect(wizard).toContainText(/(одобрено|посильно) до/)
      await wizard.getByRole('button', { name: 'Далее' }).click()
    })

    let number = ''
    await test.step('Согласия и отправка', async () => {
      await expect(wizard).toContainText(money(3_000_000))
      number = await submitWithConsents(page, 'Смирнова Анна Сергеевна')
    })

    const card = page.getByRole('dialog', { name: /Кредит без залога/ })

    await test.step('Заявка видна на первом экране и открывается карточкой', async () => {
      await openSubmittedFromHero(page, number)
      await expect(card).toBeVisible()
    })

    await test.step('Банк одобряет заявку автоматически', async () => {
      await expect(card.getByText('Банк одобрил заявку на запрошенных условиях')).toBeVisible({ timeout: 90_000 })
      await card.getByRole('button', { name: 'Принять предложение' }).click()
    })

    await test.step('Договор: проект PDF, Правила и подпись паролем', async () => {
      await expect(card.getByRole('heading', { name: `Кредитный договор № ${number}` })).toBeVisible({ timeout: 60_000 })
      const draftButton = card.getByRole('button', { name: 'Скачать проект (PDF)' })
      await expect(draftButton).toBeVisible({ timeout: 60_000 })
      const [draft] = await Promise.all([page.waitForEvent('download'), draftButton.click()])
      expect(draft.suggestedFilename()).toMatch(/\.pdf$/)
      await expect(card.getByText('Проект скачан — подписываете ровно его')).toBeVisible()

      await card.getByRole('checkbox', { name: /Принимаю/ }).check()
      await card.getByRole('textbox', { name: 'Подтвердите паролем от кабинета' }).fill(DEMO_PASSWORD)
      await card.getByRole('button', { name: 'Подписать договор' }).click()
    })

    const signedPath = testInfo.outputPath('signed.pdf')

    await test.step('Подписи сторон и выдача', async () => {
      await expect(card.getByText('Договор подписан сторонами, кредит выдан')).toBeVisible({ timeout: 90_000 })
      await expect(card.getByRole('region', { name: 'Подпись: заёмщик' })).toContainText('простая электронная подпись')
      await expect(card.getByRole('region', { name: 'Подпись: банк' })).toContainText('усиленная электронная подпись')
      const [signed] = await Promise.all([
        page.waitForEvent('download'),
        card.getByRole('button', { name: 'Скачать подписанный (PDF)' }).click(),
      ])
      await signed.saveAs(signedPath)
    })

    await test.step('Проверка подлинности по ссылке из QR и сверка скачанного файла', async () => {
      const [verify] = await Promise.all([
        page.context().waitForEvent('page'),
        card.getByRole('link', { name: 'Проверить подлинность' }).click(),
      ])
      await expect(verify.getByRole('heading', { name: 'Проверка электронного договора' })).toBeVisible()
      await expect(verify.getByText('Договор есть в архиве банка и подписан сторонами')).toBeVisible()
      await expect(verify.getByText(number)).toBeVisible()
      await expect(verify.getByRole('note').filter({ hasText: 'Журнал подписания цел' })).toBeVisible()

      const fileInput = verify.getByLabel('Выберите PDF или перетащите его сюда')
      await fileInput.setInputFiles(signedPath)
      await expect(verify.getByRole('status').filter({ hasText: 'Документ подлинный и не изменялся' })).toBeVisible()

      // Тот же файл с одним изменённым байтом подпись банка уже не проходит
      const tampered = readFileSync(signedPath)
      const middle = Math.floor(tampered.length / 2)
      tampered[middle] = tampered[middle]! ^ 0xff
      const tamperedPath = testInfo.outputPath('tampered.pdf')
      writeFileSync(tamperedPath, tampered)
      await fileInput.setInputFiles(tamperedPath)
      await expect(verify.getByRole('alert')).toBeVisible()
    })
  })
})
