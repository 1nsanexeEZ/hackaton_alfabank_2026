import { defineConfig, devices } from '@playwright/test'

/**
 * Сквозные тесты кабинета клиента на запущенном стенде: `docker compose up` из корня репозитория.
 * Адрес стенда — E2E_BASE_URL, по умолчанию тот, что поднимает compose без .env.
 */
const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:8080'

export default defineConfig({
  testDir: './tests',
  globalSetup: './support/global-setup.ts',
  // Решение банка асинхронное: заявка проходит конвейер за секунды, но на холодном стенде дольше
  timeout: 120_000,
  expect: { timeout: 15_000 },
  // Сценарии делят стенд и демо-компании: файлы по очереди, чтобы не мешать друг другу
  workers: 1,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL,
    locale: 'ru-RU',
    timezoneId: 'Europe/Moscow',
    // Анимации входа и окон при reduced motion короткие: тест не ждёт полёт букв
    contextOptions: { reducedMotion: 'reduce' },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
})
