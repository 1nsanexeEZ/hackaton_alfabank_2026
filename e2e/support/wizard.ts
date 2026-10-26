import { readFileSync } from 'node:fs'

import { expect, type Locator, type Page } from '@playwright/test'

import { applicationWizard, choose, money } from './ui'

export interface LoanTerms {
  purpose: string
  product: string
  amount: number
  termMonths: number
  /** Как срок пишет сайт: «2 года», «1 год» */
  termLabel: string
}

/** Шаг «Условия»: цель, продукт, сумма и срок — ползунками, как двигает их клиент */
export async function fillTerms(page: Page, terms: LoanTerms): Promise<void> {
  const wizard = applicationWizard(page)
  await choose(page, wizard, 'Для чего нужны деньги', terms.purpose)
  await choose(page, wizard, 'Продукт', terms.product)
  await wizard.getByRole('slider', { name: 'Сумма кредита' }).fill(String(terms.amount))
  await expect(wizard.getByRole('textbox', { name: 'Сумма кредита' })).toHaveValue(money(terms.amount))
  await wizard.getByRole('slider', { name: 'Срок' }).fill(String(terms.termMonths))
  await expect(wizard.getByRole('textbox', { name: 'Срок' })).toHaveValue(terms.termLabel)
}

/**
 * Шаг «Согласия и отправка»: кредит в своих интересах, бенефициар — как в ЕГРЮЛ, согласия на ПДн и БКИ.
 * Бенефициара называем по реестру: ответ «Никто» банк сверит с ЕГРЮЛ, увидит расхождение
 * и по 115-ФЗ отправит заявку специалисту, а не решит её автоматически.
 * Возвращает номер отправленной заявки.
 */
export async function submitWithConsents(page: Page, beneficialOwner: string): Promise<string> {
  const wizard = applicationWizard(page)
  await expect(wizard).toContainText('Согласия и отправка')
  await wizard.getByRole('radio', { name: 'Нет, в своих интересах' }).click()
  await wizard.getByRole('radio', { name: 'Есть такие — назову' }).click()
  await wizard.getByRole('textbox', { name: 'ФИО или наименование' }).fill(beneficialOwner)
  await expect(wizard.getByRole('button', { name: 'Владеет больше 25%' })).toHaveAttribute('aria-pressed', 'true')
  // Согласия могли прийти из профиля уже отмеченными — check() их не снимет
  await wizard.getByRole('checkbox', { name: 'Согласен на обработку персональных данных' }).check()
  await wizard.getByRole('checkbox', { name: /запрос кредитной истории компании/ }).check()
  await wizard.getByRole('button', { name: 'Отправить заявку' }).click()

  const submitted = wizard.getByRole('heading', { name: /Заявка № \S+ отправлена/ })
  await expect(submitted).toBeVisible()
  const number = /№ (\S+)/.exec((await submitted.textContent()) ?? '')?.[1]
  if (!number) throw new Error('Мастер не показал номер отправленной заявки')
  return number
}

/** «Готово» в мастере → карточка заявки на первом экране → «Подробнее о заявке» */
export async function openSubmittedFromHero(page: Page, number: string): Promise<void> {
  await applicationWizard(page).getByRole('button', { name: 'Готово' }).click()
  const hero = page.getByRole('article', { name: `Ваша заявка № ${number}` })
  await expect(hero).toBeVisible()
  await hero.getByRole('button', { name: 'Подробнее о заявке' }).click()
}

/** Мастер заявки с главной: «Оформить заявку» на первом экране вошедшим клиентом */
export async function startApplication(page: Page, company: string): Promise<void> {
  await page.goto('/')
  await page.getByRole('main').getByRole('button', { name: 'Оформить заявку' }).first().click()
  await expect(applicationWizard(page)).toContainText(company)
}

export interface UploadFile {
  name: string
  mimeType: string
  buffer: Buffer
}

/** Небольшой PDF для документов заявки: банк проверяет формат и размер, а не содержимое */
export const pdf = (name: string): UploadFile => ({ name, mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4\n% e2e\n') })

/** Документ на шаге «Анкета и документы»: «Выбрать файл» в строке документа — файл загружен, когда его можно удалить */
export async function uploadDocument(page: Page, title: string, file: UploadFile): Promise<void> {
  const row = applicationWizard(page).getByRole('listitem').filter({ hasText: title })
  const [chooser] = await Promise.all([page.waitForEvent('filechooser'), row.getByRole('button', { name: /Выбрать файл|Добавить файл/ }).click()])
  await chooser.setFiles(file)
  await expect(row.getByRole('button', { name: `Удалить ${file.name}` })).toBeVisible()
}

/** Выписка по счёту из сидов бэкенда (backend/seed/statements): по ней банк строит прогноз кассового разрыва */
export const statement = (company: string): UploadFile => ({
  name: `${company}.csv`,
  mimeType: 'text/csv',
  buffer: readFileSync(new URL(`../../backend/seed/statements/${company}.csv`, import.meta.url)),
})

/** Ответ на запрос банка в карточке заявки: каждый документ — «Загрузить», затем «Отправить ответ банку» */
export async function answerInfoRequest(page: Page, card: Locator, uploads: { title: string; file: UploadFile }[]): Promise<void> {
  await expect(card.getByRole('heading', { name: 'Банку нужны данные' })).toBeVisible()
  for (const { title, file } of uploads) {
    const row = card.getByRole('listitem').filter({ hasText: title })
    const [chooser] = await Promise.all([page.waitForEvent('filechooser'), row.getByRole('button', { name: /Загрузить|Добавить файл/ }).click()])
    await chooser.setFiles(file)
    await expect(row).toContainText(file.name)
  }
  await card.getByRole('button', { name: 'Отправить ответ банку' }).click()
}
