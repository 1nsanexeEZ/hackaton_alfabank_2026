import type { FullConfig } from '@playwright/test'

/** Стенд не поднят — падаем сразу с понятной подсказкой, а не таймаутом в первом тесте */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0]?.use.baseURL ?? 'http://localhost:8080'
  const url = new URL('/api/ready', baseURL)
  let problem: string | null = null
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(10_000) })
    if (!response.ok) problem = `ответ ${response.status}: ${await response.text()}`
  } catch (error) {
    problem = error instanceof Error ? error.message : String(error)
  }
  if (problem) {
    throw new Error(
      `Стенд ${baseURL} не готов (${url}: ${problem}).\n` +
        'Поднимите его из корня репозитория: docker compose up -d --build --wait\n' +
        'Стенд на другом порту — укажите адрес: E2E_BASE_URL=http://localhost:8081 npm test',
    )
  }
}
