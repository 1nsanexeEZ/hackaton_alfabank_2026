import { expect, type Page } from '@playwright/test'

import type { DemoAccount } from './accounts'

/**
 * Рабочее место сотрудника банка (/admin): своя сессия, независимая от сайта клиента.
 * Вход — демо-кнопкой на экране входа, как и у клиентов: кнопки есть, пока DEMO_LOGIN_ENABLED=true.
 */
export async function signInStaff(page: Page, account: DemoAccount): Promise<void> {
  await page.goto('/admin')
  await expect(page.getByRole('heading', { name: 'Вход', level: 2 })).toBeVisible()
  // Кнопка демо-входа подписана ролью, именем и логином — логин её однозначно выделяет
  await page.getByRole('button', { name: account.login }).click()
  // Сверяем путь, а не адрес целиком: у экрана входа в адресе есть ?redirect=/admin/dashboard
  await expect(page).toHaveURL((url) => url.pathname === '/admin/dashboard')
}

/** Раздел рабочего места через боковое меню: «Заявки», «Скоринг», «Продукты»… */
export async function openSection(page: Page, name: string): Promise<void> {
  await page.getByRole('navigation', { name: 'Разделы админки' }).getByRole('link', { name, exact: true }).click()
  await expect(page.getByRole('heading', { name, level: 1 })).toBeVisible()
}

/**
 * Заявка из очереди специалиста. Задача появляется, когда конвейер передал заявку человеку, —
 * пока её нет, перечитываем очередь.
 */
export async function openFromQueue(page: Page, number: string): Promise<void> {
  await openSection(page, 'Заявки')
  const link = page.getByRole('link', { name: `Открыть заявку ${number}` })
  await expect(async () => {
    await page.reload()
    await expect(link).toBeVisible({ timeout: 3_000 })
  }).toPass({ timeout: 90_000 })
  await link.click()
  await expect(page.getByRole('heading', { name: `Заявка ${number}`, level: 1 })).toBeVisible()
}

export interface TaskDecision {
  decision: 'Одобрить' | 'Контрпредложение' | 'Запросить данные' | 'Отказать'
  amount?: number
  termMonths?: number
  rate?: string
  /** Что запросить у клиента — подписи галочек формы */
  documents?: string[]
  comment: string
}

/**
 * Решение по задаче андеррайтера в карточке заявки: «Взять в работу», исход, условия и комментарий —
 * его клиент и банк увидят в истории заявки.
 */
export async function decideTask(page: Page, decision: TaskDecision): Promise<void> {
  const claim = page.getByRole('button', { name: 'Взять в работу' })
  if (await claim.isVisible()) await claim.click()
  const outcome = page.getByRole('group', { name: 'Решение' })
  await outcome.getByRole('button', { name: decision.decision }).click()
  await expect(outcome.getByRole('button', { name: decision.decision })).toHaveAttribute('aria-pressed', 'true')
  if (decision.amount !== undefined) await page.getByRole('textbox', { name: 'Сумма, ₽' }).fill(String(decision.amount))
  if (decision.termMonths !== undefined) await page.getByRole('textbox', { name: 'Срок, мес.' }).fill(String(decision.termMonths))
  if (decision.rate !== undefined) await page.getByRole('textbox', { name: 'Ставка, %' }).fill(decision.rate)
  if (decision.documents) {
    const requested = page.getByRole('group', { name: 'Что запросить у клиента' })
    for (const box of await requested.getByRole('checkbox').all()) await box.uncheck()
    for (const title of decision.documents) await requested.getByRole('checkbox', { name: title }).check()
  }
  await page.getByRole('textbox', { name: 'Комментарий' }).fill(decision.comment)
  await page.getByRole('button', { name: 'Вынести решение' }).click()
  await expect(page.getByRole('button', { name: 'Вынести решение' })).toBeHidden()
}
