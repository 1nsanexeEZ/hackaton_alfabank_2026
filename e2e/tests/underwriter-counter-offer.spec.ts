import { expect, test } from '@playwright/test'

import { IVANOV, UNDERWRITER, VECTOR_DIRECTOR } from '../support/accounts'
import { closeActiveApplications } from '../support/api'
import { decideTask, openFromQueue, signInStaff } from '../support/staff'
import { applicationWizard, money, signIn } from '../support/ui'
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
 * Исход «на иных условиях»: автоматика отдаёт заявку андеррайтеру, он делает встречное предложение
 * на меньшую сумму, клиент видит в карточке, что изменилось. Клиент и сотрудник — в разных окнах.
 */
test.describe('S-2: ИП с умеренным риском — андеррайтер запрашивает выписку и предлагает меньшую сумму', () => {
  test.beforeEach(async ({ request }) => {
    await closeActiveApplications(request, IVANOV, 'UNSECURED')
  })

  test('ИП Иванов: проверка моделями, выписка по запросу, прогноз кассового разрыва и встречное предложение', async ({
    page,
    browser,
  }) => {
    const wizard = applicationWizard(page)
    const card = page.getByRole('dialog', { name: /Кредит без залога/ })
    let number = ''

    await test.step('ИП подаёт 5 млн ₽ на 2 года с налоговой декларацией', async () => {
      await signIn(page, IVANOV)
      await startApplication(page, 'ИП Иванов Иван Иванович')
      await fillTerms(page, {
        purpose: 'Пополнение оборотных средств',
        product: 'Кредит без залога',
        amount: 5_000_000,
        termMonths: 24,
        termLabel: '2 года',
      })
      await wizard.getByRole('button', { name: 'Далее' }).click()
      await uploadDocument(page, 'Налоговая декларация', pdf('tax-return-2025.pdf'))
      await wizard.getByRole('button', { name: 'Далее' }).click()
      number = await submitWithConsents(page, 'Иванов Иван Иванович')
      await openSubmittedFromHero(page, number)
      await expect(card.getByText('Заявку смотрит специалист банка')).toBeVisible({ timeout: 90_000 })
    })

    const staff = await browser.newPage()

    await test.step('Андеррайтер видит обе модели и что прогноза кассового разрыва нет — запрашивает выписку', async () => {
      await signInStaff(staff, UNDERWRITER)
      await openFromQueue(staff, number)
      const scoring = staff.getByRole('main')
      await expect(scoring.getByText('PD-модель', { exact: true }).first()).toBeVisible()
      await expect(scoring.getByText('ML-модель', { exact: true }).first()).toBeVisible()
      await expect(scoring.getByText(/Клиент не загружал выписку по счёту/)).toBeVisible()
      await expect(staff.getByText('Модели видят умеренный риск').first()).toBeVisible()
      await decideTask(staff, {
        decision: 'Запросить данные',
        documents: ['Выписка по расчётному счёту за 6 месяцев (CSV)'],
        comment: 'Нужна выписка за 6 месяцев: проверим поток и кассовые разрывы',
      })
    })

    await test.step('Клиент загружает выписку CSV и отвечает банку', async () => {
      await expect(card.getByText('Нужна выписка за 6 месяцев: проверим поток и кассовые разрывы')).toBeVisible({ timeout: 60_000 })
      await answerInfoRequest(page, card, [{ title: 'Выписка по расчётному счёту', file: statement('ivanov') }])
      await expect(card.getByText('Заявку смотрит специалист банка')).toBeVisible({ timeout: 90_000 })
    })

    await test.step('С выпиской андеррайтер видит прогноз кассового разрыва и предлагает 3 млн ₽', async () => {
      await openFromQueue(staff, number)
      await expect(staff.getByText(/Клиент не загружал выписку по счёту/)).toBeHidden()
      // Выписка Иванова — с разрывом в прогнозе (backend/seed/statements/ivanov.csv)
      await expect(staff.getByText('Прогноз: кассовый разрыв')).toBeVisible()
      await expect(staff.getByRole('img', { name: /Чистый поток по месяцам и прогноз остатка: кассовый разрыв в/ })).toBeVisible()
      await decideTask(staff, {
        decision: 'Контрпредложение',
        amount: 3_000_000,
        termMonths: 24,
        comment: 'Обе модели в жёлтой зоне, по выписке возможен кассовый разрыв: снижаем сумму',
      })
      await expect(staff.getByText('Для клиента: Другие условия')).toBeVisible()
    })

    await test.step('Клиент видит встречное предложение: сумма меньше запрошенной', async () => {
      await expect(card.getByText('Банк предлагает другие условия')).toBeVisible({ timeout: 60_000 })
      await expect(card).toContainText(money(3_000_000))
      await expect(card.getByRole('button', { name: 'Принять предложение' })).toBeVisible()
    })

    await staff.close()
  })
})

test.describe('S-3: руководитель не совпадает с ЕГРЮЛ — ручное рассмотрение', () => {
  test.beforeEach(async ({ request }) => {
    await closeActiveApplications(request, VECTOR_DIRECTOR, 'CREDIT_LINE')
  })

  test('«Вектор»: кредитная линия на 10 млн ₽ у андеррайтера, лимит снижен до 6 млн ₽', async ({ page, browser }) => {
    const wizard = applicationWizard(page)
    const card = page.getByRole('dialog', { name: /Кредитная линия/ })
    let number = ''

    await test.step('Директор по кабинету подаёт кредитную линию с отчётностью', async () => {
      await signIn(page, VECTOR_DIRECTOR)
      await startApplication(page, 'ООО «Вектор»')
      await fillTerms(page, {
        purpose: 'Пополнение оборотных средств',
        product: 'Кредитная линия',
        amount: 10_000_000,
        termMonths: 24,
        termLabel: '2 года',
      })
      await wizard.getByRole('button', { name: 'Далее' }).click()
      await uploadDocument(page, 'Бухгалтерская отчётность', pdf('report-2025.pdf'))
      await wizard.getByRole('button', { name: 'Далее' }).click()
      // Бенефициар — как в ЕГРЮЛ: там руководитель и учредитель — Сидоров, а не директор из кабинета
      number = await submitWithConsents(page, 'Сидоров Сергей Сергеевич')
      await openSubmittedFromHero(page, number)
      await expect(card.getByText('Заявку смотрит специалист банка')).toBeVisible({ timeout: 90_000 })
    })

    const staff = await browser.newPage()

    await test.step('Андеррайтер видит расхождение с ЕГРЮЛ и снижает лимит', async () => {
      await signInStaff(staff, UNDERWRITER)
      await openFromQueue(staff, number)
      // Причина ручного рассмотрения — в решении движка; в ЕГРЮЛ руководитель Сидоров, а не директор из кабинета
      await expect(staff.getByText('Данные компании расходятся с ЕГРЮЛ').first()).toBeVisible()
      await expect(staff.getByRole('main')).toContainText('Сидоров Сергей Сергеевич')
      await decideTask(staff, {
        decision: 'Контрпредложение',
        amount: 6_000_000,
        termMonths: 24,
        comment: 'Руководитель в ЕГРЮЛ другой: снижаем лимит до подтверждения полномочий',
      })
      await expect(staff.getByText('Для клиента: Другие условия')).toBeVisible()
    })

    await test.step('Клиент видит предложение на 6 млн ₽', async () => {
      await expect(card.getByText('Банк предлагает другие условия')).toBeVisible({ timeout: 60_000 })
      await expect(card).toContainText(money(6_000_000))
    })

    await staff.close()
  })
})
