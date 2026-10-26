import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// Даты в тестах — по Москве, как у банка: результат не зависит от пояса машины
process.env.TZ = 'Europe/Moscow'

/**
 * Юнит-тесты чистой логики фронта: расчёты, правила продуктов, статусы, проверки форм.
 * Браузер не нужен — среда node; сквозные сценарии в браузере — в e2e/ (Playwright).
 */
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    include: ['src/**/*.test.ts'],
    environment: 'node',
  },
})
