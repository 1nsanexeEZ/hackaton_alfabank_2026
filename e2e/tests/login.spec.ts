import { expect, test } from '@playwright/test'

import { DEMO_PASSWORD, ROMASHKA_OWNER } from '../support/accounts'
import { loginDrawer, signIn } from '../support/ui'

/** Вход клиента на сайте: по паролю и в демо-учётку, ошибки входа, выход */
test.describe('Вход в кабинет', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.getByRole('banner').getByRole('button', { name: 'Войти' }).click()
  })

  test('пустая форма — подсказки у полей', async ({ page }) => {
    const drawer = loginDrawer(page)
    await drawer.getByRole('button', { name: 'Войти', exact: true }).click()
    await expect(drawer.getByText('Введите email или телефон')).toBeVisible()
    await expect(drawer.getByText('Введите пароль')).toBeVisible()
  })

  test('неверный пароль — понятная ошибка, вход не выполнен', async ({ page }) => {
    const drawer = loginDrawer(page)
    await drawer.getByRole('textbox', { name: 'Email или телефон' }).fill(ROMASHKA_OWNER.login)
    await drawer.getByRole('textbox', { name: 'Пароль' }).fill('wrong-password')
    await drawer.getByRole('button', { name: 'Войти', exact: true }).click()
    await expect(drawer.getByRole('alert')).toBeVisible()
    await expect(page.getByRole('banner').getByRole('button', { name: /Профиль/ })).toHaveCount(0)
  })

  test('учётка сотрудника на сайт не пускает', async ({ page }) => {
    const drawer = loginDrawer(page)
    await drawer.getByRole('textbox', { name: 'Email или телефон' }).fill('underwriter@bank.test')
    await drawer.getByRole('textbox', { name: 'Пароль' }).fill(DEMO_PASSWORD)
    await drawer.getByRole('button', { name: 'Войти', exact: true }).click()
    await expect(drawer.getByRole('alert')).toContainText('сотрудник')
  })

  test('вход по телефону и паролю ведёт в профиль', async ({ page }) => {
    const drawer = loginDrawer(page)
    await drawer.getByRole('textbox', { name: 'Email или телефон' }).fill('8 (999) 000-00-01')
    await drawer.getByRole('textbox', { name: 'Пароль' }).fill(DEMO_PASSWORD)
    await drawer.getByRole('button', { name: 'Войти', exact: true }).click()
    await expect(drawer).toBeHidden()
    await expect(page).toHaveURL(/\/profile$/)
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Смирнова Анна Сергеевна')
    await expect(page.getByRole('banner').getByRole('button', { name: `Профиль: ${ROMASHKA_OWNER.shortName}` })).toBeVisible()
  })
})

test('сессия переживает перезагрузку, выход её закрывает', async ({ page }) => {
  await signIn(page, ROMASHKA_OWNER)
  const profileButton = page.getByRole('banner').getByRole('button', { name: `Профиль: ${ROMASHKA_OWNER.shortName}` })
  await page.reload()
  await expect(profileButton).toBeVisible()

  await page.getByRole('button', { name: 'Выйти из кабинета' }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByRole('banner').getByRole('button', { name: 'Войти' })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('banner').getByRole('button', { name: 'Войти' })).toBeVisible()
  await expect(profileButton).toHaveCount(0)
})
