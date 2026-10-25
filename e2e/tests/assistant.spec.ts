import { expect, test } from '@playwright/test'

import { ROMASHKA_OWNER } from '../support/accounts'
import { loginDrawer, signIn } from '../support/ui'

/**
 * Умный помощник работает и без модели: без профиля compose `ai` отвечает по шаблонам.
 * Модель на CPU отвечает дольше — до таймаута ASSISTANT_LLM_TIMEOUT_S (25 с), потом тоже шаблон.
 */
test.describe('Умный помощник', () => {
  test('гостя кнопка помощника ведёт на вход', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('banner').getByRole('button', { name: /^Умный помощник/ }).click()
    await expect(loginDrawer(page)).toBeVisible()
  })

  test('отвечает на вопрос о платеже и закрывается по Esc', async ({ page }) => {
    await signIn(page, ROMASHKA_OWNER)
    const button = page.getByRole('banner').getByRole('button', { name: /^Умный помощник/ })
    await button.click()

    const chat = page.getByRole('dialog', { name: 'Умный помощник' })
    const log = chat.getByRole('log', { name: 'Диалог с помощником' })
    await expect(log).toContainText('Здравствуйте! Чем помочь?')
    await expect(chat.getByRole('button', { name: 'Какие кредиты подойдут?' })).toBeVisible()

    const question = 'Сколько я буду платить за 3 млн на 2 года?'
    const input = chat.getByRole('textbox', { name: 'Вопрос помощнику' })
    await input.fill(question)
    await chat.getByRole('button', { name: 'Отправить вопрос' }).click()
    await expect(log).toContainText(question)
    await expect(input).toHaveValue('')
    // Ответ с суммой платежа в рублях — по шаблону или от модели
    await expect(log.getByText(/₽/).last()).toBeVisible({ timeout: 60_000 })
    await expect(chat.getByRole('button', { name: 'Новый диалог' })).toBeEnabled({ timeout: 60_000 })

    await page.keyboard.press('Escape')
    await expect(chat).toBeHidden()
    await expect(button).toBeFocused()
  })
})
