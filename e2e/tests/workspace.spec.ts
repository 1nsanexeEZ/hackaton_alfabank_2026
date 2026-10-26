import { expect, test } from '@playwright/test'

import { ADMIN, UNDERWRITER, ZAKAT_OWNER } from '../support/accounts'
import { closeActiveApplications, submitApplication } from '../support/api'
import { openSection, signInStaff } from '../support/staff'

/**
 * Рабочее место сотрудника банка (/admin): экраны, с которыми работают андеррайтер и администратор.
 * Решения по задачам — в сценариях S-2…S-10; здесь — что сотрудник видит и куда может попасть.
 */
test.describe('Рабочее место андеррайтера', () => {
  test.beforeEach(async ({ page }) => {
    await signInStaff(page, UNDERWRITER)
  })

  test('вход ведёт на обзор, без сессии — экран входа, «Выйти» закрывает сессию', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Здравствуйте, Андрей', level: 1 })).toBeVisible()
    await expect(page.getByRole('complementary').getByRole('link', { name: /Андрей Андеррайтеров/ })).toBeVisible()

    await page.getByRole('button', { name: 'Выйти' }).click()
    await expect(page).toHaveURL((url) => url.pathname === '/admin/login')
    // Раздел без сессии — экран входа, после входа вернёт туда же
    await page.goto('/admin/scoring')
    await expect(page).toHaveURL((url) => url.pathname === '/admin/login' && url.searchParams.get('redirect') === '/admin/scoring')
    await expect(page.getByRole('heading', { name: 'Вход', level: 2 })).toBeVisible()
  })

  test('обзор: показатели, период и настройка панели', async ({ page }) => {
    const kpi = page.getByRole('list', { name: 'Ключевые показатели' })
    await expect(kpi.getByRole('listitem')).toHaveCount(4)
    for (const tile of ['Заявок', 'На рассмотрении', 'Одобрено', 'Время до решения']) await expect(kpi).toContainText(tile)

    const period = page.getByRole('group', { name: /Период для решений по дням/ })
    await period.getByRole('button', { name: '7 дней' }).click()
    await expect(period.getByRole('button', { name: '7 дней' })).toHaveAttribute('aria-pressed', 'true')

    // Модуль можно скрыть и вернуть раскладку по умолчанию
    const funnel = page.getByRole('main').getByRole('heading', { name: 'Воронка заявок', level: 2 })
    await expect(funnel).toBeVisible()
    await page.getByRole('button', { name: 'Настроить панель' }).click()
    await expect(page.getByRole('heading', { name: 'Модули панели' })).toBeVisible()
    await page.getByRole('button', { name: 'Скрыть «Воронка заявок»' }).click()
    await expect(funnel).toBeHidden()
    await page.getByRole('button', { name: 'Как было' }).click()
    await expect(funnel).toBeVisible()
  })

  test('заявки: очередь специалиста, все заявки банка и карточка с решением движка', async ({ page, request }) => {
    // Своя заявка для карточки: «Закат» — отказ по стоп-факторам до скоринга (S-4)
    await closeActiveApplications(request, ZAKAT_OWNER, 'UNSECURED')
    const { number } = await submitApplication(request, ZAKAT_OWNER, {
      productCode: 'UNSECURED',
      amount: 2_000_000,
      termMonths: 12,
      beneficialOwner: 'Закатов Олег Олегович',
    })

    await openSection(page, 'Заявки')
    await expect(page.getByRole('group', { name: 'Что показать' }).getByRole('button', { name: 'Очередь задач' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    await expect(page.getByRole('group', { name: 'Вид проверки' })).toBeVisible()

    await page.getByRole('group', { name: 'Что показать' }).getByRole('button', { name: 'Все заявки' }).click()
    await expect(page).toHaveURL(/view=all/)
    await page.getByRole('group', { name: 'Какие заявки показать' }).getByRole('button', { name: 'Отказ и закрытые' }).click()
    const link = page.getByRole('link', { name: `Открыть заявку ${number}` })
    // Решение асинхронное: пока заявка не дошла до отказа, перечитываем список
    await expect(async () => {
      await page.reload()
      await expect(link).toBeVisible({ timeout: 3_000 })
    }).toPass({ timeout: 90_000 })
    await link.click()

    await expect(page.getByRole('heading', { name: `Заявка ${number}`, level: 1 })).toBeVisible()
    await expect(page.getByRole('group', { name: 'Схема маршрута заявки по этапам' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Решение движка', level: 2 })).toBeVisible()
    await expect(page.getByText('Компания ликвидируется').first()).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Внешние источники', level: 2 })).toBeVisible()
    // Отказ по стоп-факторам — задачи андеррайтеру нет
    await expect(page.getByRole('button', { name: 'Взять в работу' })).toHaveCount(0)
  })

  test('проверка по ИНН: компания в ликвидации проверку не проходит', async ({ page }) => {
    await openSection(page, 'Проверка по ИНН')
    await page.getByRole('button', { name: 'Закат — ликвидация' }).click()
    const result = page.getByRole('status')
    await expect(result).toContainText('Не пройдена')
    await expect(result).toContainText('ООО «Закат»')
    await expect(page.getByText('В процессе ликвидации').first()).toBeVisible()
  })

  test('скоринг: две модели, зоны и фильтр заявок', async ({ page }) => {
    await openSection(page, 'Скоринг')
    await expect(page.getByRole('heading', { name: 'Грейды', level: 2 })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Зоны двух моделей', level: 2 })).toBeVisible()
    for (const zone of ['зелёная зона', 'жёлтая зона', 'красная зона']) {
      await expect(page.getByRole('rowheader', { name: zone })).toBeVisible()
    }
    const filter = page.getByRole('group', { name: 'Какие заявки показать' })
    await filter.getByRole('button', { name: 'Ручная проверка' }).click()
    await expect(filter.getByRole('button', { name: 'Ручная проверка' })).toHaveAttribute('aria-pressed', 'true')
  })

  test('продукты: каталог из девяти продуктов, андеррайтеру — только просмотр', async ({ page }) => {
    await openSection(page, 'Продукты')
    await expect(page.getByText('Только просмотр продуктов в продаже: вести каталог может администратор.')).toBeVisible()
    for (const product of ['Кредит без залога', 'Кредитная линия', 'Бизнес-ипотека', 'Кредит на запуск бизнеса']) {
      await expect(page.getByRole('heading', { name: product, level: 2 })).toBeVisible()
    }
    await expect(page.getByRole('main').getByRole('heading', { level: 2 })).toHaveCount(9)
    await expect(page.getByRole('button', { name: 'Новый продукт' })).toHaveCount(0)
  })

  test('модель и политика: действующие версии и примерка на прошлых заявках', async ({ page }) => {
    await openSection(page, 'Модель и политика')
    await expect(page.getByRole('row', { name: /^pd_model_v\d+ .*Действует/ })).toBeVisible()
    await page.getByRole('group', { name: 'Чьи версии показать' }).getByRole('button', { name: 'Кредитная политика' }).click()
    await expect(page.getByRole('row', { name: /^policy_v\d+ .*Действует/ })).toBeVisible()

    await page.getByRole('group', { name: 'Чьи версии показать' }).getByRole('button', { name: 'PD-модель' }).click()
    await page.getByRole('row', { name: /Действует/ }).getByRole('link').click()
    await expect(page.getByRole('heading', { name: /^pd_model_v\d+$/, level: 1 })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Границы грейдов' })).toBeVisible()
    await page.getByRole('group', { name: 'Раздел версии' }).getByRole('button', { name: 'Примерка' }).click()
    await expect(page.getByRole('group', { name: 'Сколько последних заявок пересчитать' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Примерить' })).toBeVisible()
  })

  test('ключевая ставка; пользователи и роли андеррайтеру недоступны', async ({ page }) => {
    await openSection(page, 'Ключевая ставка')
    await expect(page.getByRole('heading', { name: 'Действует сегодня' })).toBeVisible()
    await expect(page.getByRole('main')).toContainText(/\d+(,\d+)?%/)

    const navigation = page.getByRole('navigation', { name: 'Разделы админки' })
    await expect(navigation.getByRole('link', { name: 'Пользователи' })).toHaveCount(0)
    await expect(navigation.getByRole('link', { name: 'Роли и права' })).toHaveCount(0)
    // Раздел без права по прямой ссылке не открывается — обзор
    await page.goto('/admin/users')
    await expect(page).toHaveURL((url) => url.pathname === '/admin/dashboard')
  })
})

test.describe('Рабочее место администратора', () => {
  test.beforeEach(async ({ page }) => {
    await signInStaff(page, ADMIN)
  })

  test('пользователи: сотрудники и клиенты, поиск', async ({ page }) => {
    await openSection(page, 'Пользователи')
    const list = page.getByRole('main').getByRole('list')
    await expect(list).toContainText('underwriter@bank.test')
    await expect(list).toContainText('owner@romashka.test')
    await page.getByRole('searchbox', { name: 'Поиск' }).fill('ivanov')
    await expect(list).toContainText('ivanov@ip.test')
    await expect(list).not.toContainText('owner@romashka.test')
  })

  test('роли и права: у андеррайтера — заявки и задачи, без пользователей и ролей', async ({ page }) => {
    await openSection(page, 'Роли и права')
    const matrix = page.getByRole('table', { name: 'Права роли Андеррайтер' })
    await expect(matrix.getByRole('row', { name: /^Заявки есть/ })).toBeVisible()
    await expect(matrix.getByRole('row', { name: 'Пользователи нет нет нет нет' })).toBeVisible()
    await expect(matrix.getByRole('row', { name: 'Роли нет нет нет нет' })).toBeVisible()
    await expect(page.getByRole('main')).toContainText('Решать задачи')
  })

  test('продукты: администратор ведёт каталог', async ({ page }) => {
    await openSection(page, 'Продукты')
    await expect(page.getByRole('button', { name: 'Новый продукт' })).toBeVisible()
    const filter = page.getByRole('group', { name: 'Какие продукты показать' })
    await expect(filter.getByRole('button', { name: /^Все · \d+$/ })).toHaveAttribute('aria-pressed', 'true')
    await filter.getByRole('button', { name: /^В продаже/ }).click()
    await expect(page.getByRole('heading', { name: 'Кредит без залога', level: 2 })).toBeVisible()
  })
})
