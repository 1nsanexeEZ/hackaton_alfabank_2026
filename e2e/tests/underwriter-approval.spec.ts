import { expect, test } from '@playwright/test'

import { ROMASHKA_OWNER, SBOY_OWNER, UNDERWRITER } from '../support/accounts'
import { closeActiveApplications } from '../support/api'
import { decideTask, openFromQueue, signInStaff } from '../support/staff'
import { applicationWizard, signIn } from '../support/ui'
import { fillTerms, openSubmittedFromHero, pdf, startApplication, submitWithConsents, uploadDocument } from '../support/wizard'

/**
 * Заявки, которые автоматика не решает сама, а отдаёт андеррайтеру. Клиент и сотрудник — в разных окнах:
 * решение андеррайтера в /admin клиент видит в карточке заявки без перезагрузки.
 */
test.describe('S-6: бюро кредитных историй недоступно — решает андеррайтер', () => {
  test.beforeEach(async ({ request }) => {
    await closeActiveApplications(request, SBOY_OWNER, 'UNSECURED')
  })

  test('«Сбой» уходит специалисту, андеррайтер видит неответивший источник и одобряет', async ({ page, browser }) => {
    let number = ''
    const card = page.getByRole('dialog', { name: /Кредит без залога/ })

    await test.step('Клиент подаёт кредит без залога на 1 млн ₽ и 12 месяцев', async () => {
      await signIn(page, SBOY_OWNER)
      await startApplication(page, 'ООО «Сбой»')
      await fillTerms(page, {
        purpose: 'Пополнение оборотных средств',
        product: 'Кредит без залога',
        amount: 1_000_000,
        termMonths: 12,
        termLabel: '1 год',
      })
      await page.getByRole('dialog', { name: 'Заявка на кредит' }).getByRole('button', { name: 'Далее' }).click()
      number = await submitWithConsents(page, 'Сбоев Семён Семёнович')
      await openSubmittedFromHero(page, number)
      // БКИ отвечает 503 всегда: по неполным данным автоматика не решает
      await expect(card.getByText('Заявку смотрит специалист банка')).toBeVisible({ timeout: 90_000 })
    })

    const staff = await browser.newPage()

    await test.step('Андеррайтер находит заявку в очереди: спорная, источник данных не ответил', async () => {
      await signInStaff(staff, UNDERWRITER)
      await openFromQueue(staff, number)
      await expect(staff.getByText('Источник данных не ответил').first()).toBeVisible()
      await expect(staff.getByText('Бюро кредитных историй: не ответил')).toBeVisible()
      await expect(staff.getByText(/Данные неполные — решает специалист/)).toBeVisible()
    })

    await test.step('Андеррайтер берёт задачу и одобряет на условиях движка', async () => {
      await decideTask(staff, {
        decision: 'Одобрить',
        comment: 'БКИ недоступно, но обороты по счёту и отчётность подтверждают платёжеспособность',
      })
      // Маршрут заявки переходит на «Оффер»: клиенту — одобрено
      await expect(staff.getByRole('button', { name: 'Оффер: Заявка здесь' })).toBeVisible()
      await expect(staff.getByText('Для клиента: Одобрена')).toBeVisible()
    })

    await test.step('Клиент видит одобрение в открытой карточке', async () => {
      await expect(card.getByText('Банк одобрил заявку на запрошенных условиях')).toBeVisible({ timeout: 60_000 })
      await expect(card.getByRole('button', { name: 'Принять предложение' })).toBeVisible()
    })

    await staff.close()
  })
})

test.describe('S-7: бизнес-ипотека всегда у специалиста', () => {
  test.beforeEach(async ({ request }) => {
    await closeActiveApplications(request, ROMASHKA_OWNER, 'MORTGAGE')
  })

  test('ипотека с залогом уходит андеррайтеру; ставку ниже коридора политика возвращает, со второго раза — предложение', async ({
    page,
    browser,
  }) => {
    const wizard = applicationWizard(page)
    const card = page.getByRole('dialog', { name: /Бизнес-ипотека/ })
    let number = ''

    await test.step('Условия: недвижимость, 30 млн ₽ на 10 лет', async () => {
      await signIn(page, ROMASHKA_OWNER)
      await startApplication(page, 'ООО «Ромашка»')
      await fillTerms(page, {
        purpose: 'Покупка недвижимости',
        product: 'Бизнес-ипотека',
        amount: 30_000_000,
        termMonths: 120,
        termLabel: '10 лет',
      })
      await wizard.getByRole('button', { name: 'Далее' }).click()
    })

    await test.step('Анкета: залог на 50 млн ₽, объект и три документа', async () => {
      await expect(wizard.getByRole('heading', { name: 'Залог' })).toBeVisible()
      await expect(wizard.getByRole('combobox', { name: 'Что даёте в залог' })).toHaveText('Недвижимость')
      await wizard.getByRole('textbox', { name: 'Описание' }).fill('Офис, г. Москва, ул. Тверская, д. 10')
      await wizard.getByRole('textbox', { name: 'Оценочная стоимость, ₽' }).fill('50000000')
      await wizard.getByRole('textbox', { name: 'Стоимость, ₽', exact: true }).fill('50000000')
      await wizard.getByRole('textbox', { name: 'Адрес объекта' }).fill('г. Москва, ул. Тверская, д. 10')
      // Пока документов нет, подвал мастера перечисляет, чего не хватает
      await expect(wizard.getByRole('contentinfo')).toContainText('Не заполнено')
      await uploadDocument(page, 'Бухгалтерская отчётность', pdf('report-2025.pdf'))
      await uploadDocument(page, 'Договор купли-продажи', pdf('purchase.pdf'))
      await uploadDocument(page, 'Документы на залог', pdf('collateral.pdf'))
      await expect(wizard.getByRole('contentinfo')).not.toContainText('Не заполнено')
      await wizard.getByRole('button', { name: 'Далее' }).click()
      number = await submitWithConsents(page, 'Смирнова Анна Сергеевна')
    })

    await test.step('У ипотеки нет лимита авторешения — заявка у специалиста', async () => {
      await openSubmittedFromHero(page, number)
      await expect(card.getByText('Заявку смотрит специалист банка')).toBeVisible({ timeout: 90_000 })
    })

    const staff = await browser.newPage()

    await test.step('Андеррайтер видит причину и залог в заявке', async () => {
      await signInStaff(staff, UNDERWRITER)
      await openFromQueue(staff, number)
      await expect(staff.getByText('Сумма выше лимита авторешения').first()).toBeVisible()
      await expect(staff.getByText('Офис, г. Москва, ул. Тверская, д. 10').first()).toBeVisible()
    })

    await test.step('Одобрение под 10% — ниже коридора продукта: политика возвращает задачу с причиной', async () => {
      await decideTask(staff, { decision: 'Одобрить', rate: '10', comment: 'Залог покрывает сумму с дисконтом' })
      await expect(staff.getByText('Почему задача вернулась')).toBeVisible({ timeout: 60_000 })
      await expect(card.getByText('Заявку смотрит специалист банка')).toBeVisible()
    })

    await test.step('Повторное решение по ставке движка — клиенту предложение', async () => {
      await decideTask(staff, { decision: 'Одобрить', comment: 'Залог покрывает сумму с дисконтом, ставка по коридору продукта' })
      await expect(staff.getByText('Для клиента: Одобрена')).toBeVisible()
      await expect(card.getByText('Банк одобрил заявку на запрошенных условиях')).toBeVisible({ timeout: 60_000 })
    })

    await staff.close()
  })
})
