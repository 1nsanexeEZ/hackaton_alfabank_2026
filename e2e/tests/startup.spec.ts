import { expect, test, type Locator } from '@playwright/test'

import { START_OWNER, UNDERWRITER } from '../support/accounts'
import { closeActiveApplications, founderPrescreenPassed } from '../support/api'
import { signContract } from '../support/contract'
import { decideTask, openFromQueue, signInStaff } from '../support/staff'
import { applicationWizard, choose, signIn } from '../support/ui'
import { fillTerms, openSubmittedFromHero, pdf, startApplication, submitWithConsents, uploadDocument } from '../support/wizard'

/**
 * Ветка стартапа (S-9, S-10 из README): у компании без оборотов вместо предодобрения — проверка учредителя
 * по его личной кредитной истории, вместо матрицы риска — проектная оценка андеррайтера.
 */

const STARTUP_TERMS = {
  purpose: 'Пополнение оборотных средств',
  product: 'Кредит на запуск бизнеса',
  amount: 3_000_000,
  termMonths: 36,
  termLabel: '3 года',
}

/** Проверка учредителя: согласие на запрос его кредитной истории, затем сама проверка; уже пройдена — ничего не делаем */
async function passFounderPrescreen(scope: Locator): Promise<void> {
  const passed = scope.getByText(/Пройдена · Стартов Степан Сергеевич/)
  const consent = scope.getByRole('button', { name: 'Дать согласие' })
  const run = scope.getByRole('button', { name: /^Пройти проверку/ })
  await expect(passed.or(consent).or(run).first()).toBeVisible()
  if (await passed.isVisible()) return
  if (await consent.isVisible()) await consent.click()
  await run.click()
  await expect(passed).toBeVisible()
}

/** Стартап подаёт заявку: шаг документов — бизнес-план и финмодель, бенефициар — учредитель */
async function submitStartupApplication(page: import('@playwright/test').Page): Promise<string> {
  const wizard = applicationWizard(page)
  await fillTerms(page, STARTUP_TERMS)
  await wizard.getByRole('button', { name: 'Далее' }).click()
  await uploadDocument(page, 'Бизнес-план', pdf('business-plan.pdf'))
  await uploadDocument(page, 'Финансовая модель', pdf('financial-model.pdf'))
  await wizard.getByRole('button', { name: 'Далее' }).click()
  return submitWithConsents(page, 'Стартов Степан Сергеевич')
}

test.describe('S-9: ветка стартапа — проверка учредителя и проектная оценка андеррайтера', () => {
  test.beforeEach(async ({ request }) => {
    await closeActiveApplications(request, START_OWNER, 'STARTUP')
  })

  test('без пройденной проверки учредителя заявку на запуск бизнеса не подать', async ({ page, request }) => {
    test.skip(
      await founderPrescreenPassed(request, START_OWNER),
      'Проверка учредителя на этом стенде уже пройдена и действует 30 дней: запрет виден только на свежем стенде',
    )
    const wizard = applicationWizard(page)
    await signIn(page, START_OWNER)
    await startApplication(page, 'ООО «Старт»')
    await expect(wizard).toContainText('Компания недавно зарегистрирована — для неё кредиты на запуск бизнеса с проверкой учредителя.')
    await expect(wizard).toContainText('Проверку ещё не проходили.')
    await expect(wizard.getByRole('button', { name: 'Далее' })).toBeDisabled()
  })

  test('учредитель проходит проверку, андеррайтер оценивает проект, клиент подписывает и получает кредит', async ({ page, browser }) => {
    const wizard = applicationWizard(page)
    const card = page.getByRole('dialog', { name: /Кредит на запуск бизнеса/ })
    let number = ''

    await test.step('В мастере — проверка учредителя, затем бизнес-план и финмодель', async () => {
      await signIn(page, START_OWNER)
      await startApplication(page, 'ООО «Старт»')
      await passFounderPrescreen(wizard)
      number = await submitStartupApplication(page)
      await openSubmittedFromHero(page, number)
    })

    const staff = await browser.newPage()

    await test.step('Андеррайтер делает проектную оценку и одобряет', async () => {
      await signInStaff(staff, UNDERWRITER)
      await openFromQueue(staff, number)
      // У задачи стартапа — оценка бизнес-плана, обеспечение и господдержка: форма открывается, когда задачу взяли
      await staff.getByRole('button', { name: 'Взять в работу' }).click()
      await expect(staff.getByRole('group', { name: 'Оценка бизнес-плана' })).toBeVisible()
      await decideTask(staff, {
        decision: 'Одобрить',
        comment: 'Бизнес-план реалистичный, учредитель без просрочек',
      })
      await expect(staff.getByText('Для клиента: Одобрена')).toBeVisible()
    })

    await test.step('Клиент принимает предложение, подписывает договор, кредит выдан', async () => {
      await expect(card.getByText('Банк одобрил заявку на запрошенных условиях')).toBeVisible({ timeout: 60_000 })
      await card.getByRole('button', { name: 'Принять предложение' }).click()
      await signContract(page, card, number)
    })

    await staff.close()
  })
})

test.describe('S-10: предодобрение стартапа по бизнес-плану', () => {
  test.beforeEach(async ({ request }) => {
    await closeActiveApplications(request, START_OWNER, 'STARTUP')
  })

  test('бизнес-план в кабинете → предодобрение → заявка → андеррайтер подтверждает оценку → подпись', async ({ page, browser }) => {
    const company = page.getByRole('dialog', { name: 'Компания' })
    const card = page.getByRole('dialog', { name: /Кредит на запуск бизнеса/ })
    let number = ''

    await test.step('Учредитель заполняет бизнес-план и финмодель в «Компании»', async () => {
      await signIn(page, START_OWNER)
      await page.getByRole('main').getByRole('button', { name: 'Подробнее' }).first().click()
      await expect(company).toContainText('Бизнес-план и проектная оценка')
      await passFounderPrescreen(company)
      await company.getByRole('button', { name: /Заполнить бизнес-план|Изменить план/ }).click()
      await company.getByRole('textbox', { name: 'Описание проекта' }).fill('Кофейня у метро: зерно от обжарщика, завтраки, доставка по району')
      await company.getByRole('textbox', { name: 'Кредит, ₽' }).fill('3000000')
      await company.getByRole('textbox', { name: 'Срок, мес.' }).fill('36')
      await company.getByRole('textbox', { name: 'Свои средства, ₽' }).fill('1000000')
      await choose(page, company, 'Гарантия господдержки', 'Корпорация МСП')
      await company.getByRole('textbox', { name: 'Доля гарантии, %' }).fill('50')
      await company.getByRole('textbox', { name: 'Залог, ₽' }).fill('0')
      await company.getByRole('textbox', { name: 'Обеспечение' }).fill('Поручительство учредителя')
      // Финмодель на 24 месяца: выручка 1 млн и расходы 800 тыс. каждый месяц
      await company.getByRole('textbox', { name: 'Выручка в 1-й месяц, ₽' }).fill('1000000')
      await company.getByRole('textbox', { name: 'Рост в месяц, %' }).fill('0')
      await company.getByRole('textbox', { name: 'Расходы в месяц, ₽' }).fill('800000')
      await company.getByRole('button', { name: 'Заполнить месяцы' }).click()
      await company.getByRole('button', { name: /Сохранить план|Сохранить изменения/ }).click()
      await expect(company.getByText(/Бизнес-план · редакция \d+/)).toBeVisible()
    })

    await test.step('Банк оценивает проект и предодобряет кредит', async () => {
      await company.getByRole('button', { name: /^Оценить проект/ }).click()
      await expect(company.getByText(/Вам предодобрен кредит до [\d\s]+₽/)).toBeVisible()
      await company.getByRole('button', { name: 'Оформить заявку' }).click()
      await expect(applicationWizard(page)).toContainText('ООО «Старт»')
      number = await submitStartupApplication(page)
      // Мастер открыт из «Компании» в профиле: заявку находим на главной
      await applicationWizard(page).getByRole('button', { name: 'Готово' }).click()
      await page.goto('/')
      await page.getByRole('article', { name: `Ваша заявка № ${number}` }).getByRole('button', { name: 'Подробнее о заявке' }).click()
    })

    const staff = await browser.newPage()

    await test.step('Андеррайтер видит оценку банка в форме и подтверждает её', async () => {
      await signInStaff(staff, UNDERWRITER)
      await openFromQueue(staff, number)
      await staff.getByRole('button', { name: 'Взять в работу' }).click()
      await expect(staff.getByText('Предзаполнено по проектной оценке банка — подтвердите или поправьте.')).toBeVisible()
      await decideTask(staff, {
        decision: 'Одобрить',
        comment: 'Проект подтверждаю: финмодель реалистичная, гарантия Корпорации МСП',
      })
      await expect(staff.getByText('Для клиента: Одобрена')).toBeVisible()
    })

    await test.step('Клиент подписывает договор и получает кредит', async () => {
      await expect(card.getByText('Банк одобрил заявку на запрошенных условиях')).toBeVisible({ timeout: 60_000 })
      await card.getByRole('button', { name: 'Принять предложение' }).click()
      await signContract(page, card, number)
    })

    await staff.close()
  })
})
