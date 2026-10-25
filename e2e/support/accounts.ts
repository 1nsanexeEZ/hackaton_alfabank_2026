/**
 * Демо-учётки из сидов бэкенда (backend/seed/demo_data.py, таблица в README корня).
 * caption — подпись кнопки демо-входа: по ней тест находит учётку в панели входа.
 */
export interface DemoAccount {
  login: string
  caption: string
  /** Как шапка сайта называет вошедшего: «Профиль: Анна Смирнова» */
  shortName: string
}

export const ROMASHKA_OWNER: DemoAccount = {
  login: 'owner@romashka.test',
  caption: 'Директор ООО «Ромашка»',
  shortName: 'Анна Смирнова',
}

export const ZAKAT_OWNER: DemoAccount = {
  login: 'owner@zakat.test',
  caption: 'Директор ООО «Закат»',
  shortName: 'Олег Закатов',
}

/** Пароль всех демо-учёток (DEMO_PASSWORD в .env стенда): нужен для входа по паролю и подписи договора */
export const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? 'Demo-2026!'
