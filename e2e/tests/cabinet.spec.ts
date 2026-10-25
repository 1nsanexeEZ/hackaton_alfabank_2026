import { expect, test } from '@playwright/test'

import { ROMASHKA_OWNER } from '../support/accounts'
import { applicationWizard, signIn } from '../support/ui'

/** Кабинет клиента: профиль, компания, уведомления и список заявок — без подачи новой заявки */
test.describe('Кабинет директора «Ромашки»', () => {
  test.beforeEach(async ({ page }) => {
    await signIn(page, ROMASHKA_OWNER)
  })

  test('профиль: личные данные, согласия, компании и выход', async ({ page }) => {
    const main = page.getByRole('main')
    await expect(main.getByRole('heading', { level: 1 })).toHaveText('Смирнова Анна Сергеевна')
    for (const section of ['Личные данные', 'Согласия', 'Мои компании', 'Вход и безопасность']) {
      await expect(main.getByRole('heading', { name: section, level: 2 })).toBeVisible()
    }
    await expect(main.getByRole('heading', { name: 'Мои согласия', level: 3 })).toBeVisible()
    await expect(main.getByRole('heading', { name: 'Согласия компаний', level: 3 })).toBeVisible()
    // Компания со сверкой с реестром и правами пользователя в ней
    await expect(main.getByRole('button', { name: /ООО «Ромашка».*ИНН 7701158817/ })).toBeVisible()
    await expect(main.getByRole('button', { name: 'Выйти из кабинета' })).toBeVisible()
  })

  test('компания: реквизиты из банка, предодобрение, отчётность и участники', async ({ page }) => {
    await page.getByRole('main').getByRole('button', { name: 'Подробнее' }).first().click()
    const company = page.getByRole('dialog', { name: 'Компания' })
    await expect(company.getByRole('heading', { name: 'Реквизиты' })).toBeVisible()
    await expect(company).toContainText('7701158817')
    await expect(company).toContainText('Смирнова Анна Сергеевна')

    // Предодобрение по каждому продукту — с кнопкой «Оформить»
    await expect(company.getByRole('heading', { name: 'Предварительно одобрено' })).toBeVisible()
    const offer = company.getByRole('listitem').filter({ hasText: 'Кредит без залога' })
    await expect(offer).toContainText(/до [\d\s]+₽/)
    await expect(offer.getByRole('button', { name: 'Оформить' })).toBeVisible()

    await expect(company.getByRole('heading', { name: 'Финансовая отчётность' })).toBeVisible()
    await expect(company.getByRole('table')).toBeVisible()
    await expect(company.getByRole('heading', { name: 'Участники и полномочия' })).toBeVisible()

    // «Оформить» по предодобрению открывает мастер с этим продуктом
    await offer.getByRole('button', { name: 'Оформить' }).click()
    const wizard = applicationWizard(page)
    await expect(wizard).toBeVisible()
    await expect(wizard.getByRole('combobox', { name: 'Продукт' })).toContainText('Кредит без залога')
  })

  test('уведомления: события и новости, переключение вкладок', async ({ page }) => {
    await page.getByRole('banner').getByRole('button', { name: /^Уведомления/ }).click()
    const feed = page.getByRole('dialog', { name: 'Уведомления' })
    const tabs = feed.getByRole('group', { name: 'Что показать' })
    await expect(tabs.getByRole('button', { name: /^События/ })).toHaveAttribute('aria-pressed', 'true')
    // Сверка с ЕГРЮЛ и предодобрение приходят в ленту сразу после сидов
    await expect(feed.getByRole('listitem').first()).toBeVisible()

    await tabs.getByRole('button', { name: 'Новости для вас' }).click()
    await expect(tabs.getByRole('button', { name: 'Новости для вас' })).toHaveAttribute('aria-pressed', 'true')
    await page.keyboard.press('Escape')
    await expect(feed).toBeHidden()
  })

  test('мои заявки: фильтр и новая заявка', async ({ page }) => {
    await page.getByRole('main').getByRole('button', { name: 'Мои заявки' }).click()
    const list = page.getByRole('dialog', { name: 'Мои заявки' })
    const filter = list.getByRole('group', { name: 'Какие заявки показать' })
    await expect(filter.getByRole('button', { name: 'В работе' })).toHaveAttribute('aria-pressed', 'true')
    await filter.getByRole('button', { name: 'Все' }).click()
    await expect(filter.getByRole('button', { name: 'Все' })).toHaveAttribute('aria-pressed', 'true')

    await list.getByRole('button', { name: 'Новая заявка' }).click()
    await expect(applicationWizard(page)).toBeVisible()
    await expect(list).toBeHidden()
  })
})
