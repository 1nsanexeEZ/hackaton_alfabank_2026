import { expect, test } from '@playwright/test'

import { ROMASHKA_OWNER } from '../support/accounts'
import { signIn } from '../support/ui'

/** Поддержка: клиент задаёт вопрос, дописывает в чат и закрывает обращение */
test('клиент задаёт вопрос в поддержку и ведёт переписку', async ({ page }) => {
  await signIn(page, ROMASHKA_OWNER)
  await page.getByRole('banner').getByRole('button', { name: 'Поддержка' }).click()
  await expect(page).toHaveURL(/\/support$/)
  await expect(page.getByRole('heading', { name: 'Поддержка', level: 1 })).toBeVisible()

  // Тема уникальна для прогона: обращения с прошлых прогонов остаются в списке
  const subject = `Документы для залога — e2e ${Date.now()}`
  await page.getByRole('button', { name: 'Задать вопрос' }).click()
  await page.getByRole('button', { name: 'Отправить вопрос' }).click()
  await expect(page.getByText('Коротко — о чём вопрос')).toBeVisible()
  await expect(page.getByText('Опишите вопрос')).toBeVisible()

  await page.getByRole('textbox', { name: 'Тема' }).fill(subject)
  await page.getByRole('textbox', { name: 'Вопрос' }).fill('Какие документы нужны, если в залог идёт оборудование?')
  await page.getByRole('button', { name: 'Отправить вопрос' }).click()

  // Открылся чат обращения: тема, первое сообщение, статус очереди
  await expect(page).toHaveURL(/\/support\/[\w-]+$/)
  await expect(page.getByRole('heading', { name: subject })).toBeVisible()
  await expect(page.getByText('Какие документы нужны, если в залог идёт оборудование?')).toBeVisible()
  await expect(page.getByText('Вопрос в очереди — специалист скоро возьмёт его')).toBeVisible()

  await page.getByRole('textbox', { name: 'Сообщение' }).fill('Оборудование куплено в 2024 году.')
  await page.getByRole('button', { name: 'Отправить сообщение' }).click()
  await expect(page.getByText('Оборудование куплено в 2024 году.')).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Сообщение' })).toHaveValue('')

  await page.getByRole('button', { name: 'Закрыть обращение' }).click()
  await expect(page.getByText(/Обращение закрыто.*задайте его заново/)).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Сообщение' })).toHaveCount(0)
})
