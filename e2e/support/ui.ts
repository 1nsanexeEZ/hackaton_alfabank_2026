import { expect, type Locator, type Page } from '@playwright/test'

import type { DemoAccount } from './accounts'

/** Панель входа клиента: открывается кнопкой «Войти» в шапке или «Оформить заявку», если клиент не вошёл */
export const loginDrawer = (page: Page) => page.getByRole('dialog', { name: 'Вход в личный кабинет' })

/** Мастер заявки */
export const applicationWizard = (page: Page) => page.getByRole('dialog', { name: 'Заявка на кредит' })

/**
 * Вход в демо-учётку одной кнопкой в открытой панели входа.
 * Кнопки есть, пока на стенде DEMO_LOGIN_ENABLED=true — так compose поднимает его по умолчанию.
 */
export async function signInWithDemo(page: Page, account: DemoAccount): Promise<void> {
  const drawer = loginDrawer(page)
  // Кнопка подписана «ФИО подпись»: подпись сверяем по концу — «ИП Иванов» не путаем с «…и ИП Иванова»
  await drawer.getByRole('button', { name: new RegExp(`${escapeRegExp(account.caption)}$`) }).click()
  await expect(drawer).toBeHidden()
}

/** «Войти» в шапке главной → демо-учётка → страница профиля */
export async function signIn(page: Page, account: DemoAccount): Promise<void> {
  await page.goto('/')
  await page.getByRole('banner').getByRole('button', { name: 'Войти' }).click()
  await signInWithDemo(page, account)
  await expect(page).toHaveURL(/\/profile$/)
}

/** Свой выпадающий список сайта (SelectField): кнопка с ролью combobox, варианты — в списке поверх страницы */
export async function choose(page: Page, scope: Locator, label: string, option: string): Promise<void> {
  await scope.getByRole('combobox', { name: label }).click()
  await page.getByRole('listbox').getByRole('option', { name: option, exact: true }).click()
  await expect(page.getByRole('listbox')).toBeHidden()
}

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

/** Деньги так, как их пишет сайт: «3 000 000 ₽» с неразрывными пробелами — в проверках пробелы любые */
export const money = (amount: number) => new RegExp(`${amount.toLocaleString('ru-RU').replace(/\s/g, '\\s')}\\s₽`)
