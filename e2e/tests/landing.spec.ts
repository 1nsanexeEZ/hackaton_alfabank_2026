import { expect, test } from '@playwright/test'

import { loginDrawer } from '../support/ui'

/** Сайт глазами гостя: без входа видно продукты, подбор и расчёт платежа */
test.describe('Лендинг без входа', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('первый экран, разделы в шапке и пример заявки', async ({ page }) => {
    await expect(page).toHaveTitle(/.+/)
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Кредит для бизнеса')
    const nav = page.getByRole('banner').getByRole('navigation', { name: 'Разделы' })
    for (const section of ['Калькулятор', 'Продукты', 'Как это работает', 'Вопросы']) {
      await expect(nav.getByRole('link', { name: section })).toBeVisible()
    }
    // Гостю — иллюстрация заявки, а не данные
    await expect(page.getByRole('article', { name: 'Пример заявки в кабинете' })).toBeVisible()
    await expect(page.getByRole('banner').getByRole('button', { name: 'Войти' })).toBeVisible()
  })

  test('подбор: продукты меняются под цель кредита', async ({ page }) => {
    const purposes = page.getByRole('group', { name: 'Для чего нужны деньги' })
    const products = page.getByRole('list', { name: 'Продукты под цель' })

    await purposes.getByRole('button', { name: 'Закрыть кассовый разрыв' }).click()
    await expect(purposes.getByRole('button', { name: 'Закрыть кассовый разрыв' })).toHaveAttribute('aria-pressed', 'true')
    await expect(products.getByRole('button', { name: /^Овердрафт/ })).toBeVisible()
    await expect(products.getByRole('button', { name: /^Кредитная линия/ })).toBeVisible()
    // Кредит под залог под кассовый разрыв банк не предлагает
    await expect(products.getByRole('button', { name: /^Кредит под залог/ })).toHaveCount(0)

    await products.getByRole('button', { name: /^Овердрафт/ }).click()
    await expect(products.getByRole('button', { name: /^Овердрафт/ })).toHaveAttribute('aria-pressed', 'true')
  })

  test('расчёт: платёж пересчитывается по сумме и сроку', async ({ page }) => {
    const products = page.getByRole('list', { name: 'Продукты под цель' })
    await products.getByRole('button', { name: /^Кредит без залога/ }).click()
    await expect(products.getByRole('button', { name: /^Кредит без залога/ })).toHaveAttribute('aria-pressed', 'true')

    const payment = page.getByText('Ежемесячный платёж', { exact: true }).locator('xpath=following-sibling::p[1]')
    await expect(payment).toHaveText(/^\d[\d\s]*₽$/)
    const before = await payment.textContent()

    await page.getByRole('slider', { name: 'Сумма' }).fill('5000000')
    await page.getByRole('slider', { name: 'Срок' }).fill('60')
    await expect(page.getByText(/^5\s000\s000\s₽ на 5 лет$/)).toBeVisible()
    await expect(payment).not.toHaveText(before ?? '')
    await expect(payment).toHaveText(/^\d[\d\s]*₽$/)
    await expect(page.getByText(/Расчёт по базовой ставке продукта/)).toBeVisible()
  })

  test('каталог: девять продуктов, переход к расчёту', async ({ page }) => {
    await expect(page.getByText('01 / 09')).toBeVisible()
    await page.getByRole('button', { name: 'Показать продукт «Овердрафт»' }).first().click()
    const overdraft = page.getByRole('article').filter({ has: page.getByRole('heading', { name: 'Овердрафт', level: 3 }) })
    await expect(overdraft).toBeVisible()
    await overdraft.getByRole('button', { name: 'Рассчитать платёж' }).click()
    // Калькулятор выбирает продукт и цель, под которую он подходит
    await expect(page.getByRole('list', { name: 'Продукты под цель' }).getByRole('button', { name: /^Овердрафт/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })

  test('«Оформить заявку» гостем просит войти', async ({ page }) => {
    await page.getByRole('main').getByRole('button', { name: 'Оформить заявку' }).first().click()
    const drawer = loginDrawer(page)
    await expect(drawer).toContainText('Чтобы оформить заявку, войдите')
    await page.keyboard.press('Escape')
    await expect(drawer).toBeHidden()
  })

  test('вопросы и ответы раскрываются', async ({ page }) => {
    const question = page.getByRole('button', { name: 'Как подписать договор?' })
    await expect(question).toHaveAttribute('aria-expanded', 'false')
    await question.click()
    await expect(question).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByRole('region', { name: 'Как подписать договор?' })).toBeVisible()
  })
})

test.describe('Служебные страницы', () => {
  test('несуществующий адрес — страница 404 со ссылкой на главную', async ({ page }) => {
    await page.goto('/no-such-page')
    await expect(page.getByRole('heading', { name: 'Страница не найдена' })).toBeVisible()
    await page.getByRole('link', { name: 'На главную', exact: true }).click()
    await expect(page).toHaveURL(/\/$/)
  })

  test('проверка договора по неизвестной ссылке', async ({ page }) => {
    await page.goto('/verify/00000000-0000-0000-0000-000000000000')
    await expect(page.getByRole('heading', { name: 'Проверка электронного договора' })).toBeVisible()
    await expect(page.getByText('Документ не найден в архиве банка')).toBeVisible()
    // Не PDF файл проверка не принимает
    await page.getByLabel('Выберите PDF или перетащите его сюда').setInputFiles({
      name: 'contract.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('не договор'),
    })
    await expect(page.getByRole('alert')).toContainText('Это не PDF-файл')
  })
})
