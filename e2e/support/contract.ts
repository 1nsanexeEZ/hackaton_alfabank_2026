import { expect, type Locator, type Page } from '@playwright/test'

import { DEMO_PASSWORD } from './accounts'

/**
 * Подпись договора в карточке заявки, как в S-1: проект PDF скачан, Правила приняты, пароль от кабинета.
 * Возвращает, когда банк подписал своей подписью и выдал кредит.
 */
export async function signContract(page: Page, card: Locator, number: string): Promise<void> {
  await expect(card.getByRole('heading', { name: `Кредитный договор № ${number}` })).toBeVisible({ timeout: 60_000 })
  const draft = card.getByRole('button', { name: 'Скачать проект (PDF)' })
  await expect(draft).toBeVisible({ timeout: 60_000 })
  await Promise.all([page.waitForEvent('download'), draft.click()])
  await expect(card.getByText('Проект скачан — подписываете ровно его')).toBeVisible()
  await card.getByRole('checkbox', { name: /Принимаю/ }).check()
  await card.getByRole('textbox', { name: 'Подтвердите паролем от кабинета' }).fill(DEMO_PASSWORD)
  await card.getByRole('button', { name: 'Подписать договор' }).click()
  await expect(card.getByText('Договор подписан сторонами, кредит выдан')).toBeVisible({ timeout: 90_000 })
}
