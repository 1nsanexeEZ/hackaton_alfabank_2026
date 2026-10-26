/**
 * Демо-учётки из сидов бэкенда (backend/seed/demo_data.py, таблица в README корня).
 * caption — подпись кнопки демо-входа целиком: по ней тест находит учётку в панели входа.
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

/** Бухгалтер «Ромашки»: подаёт заявки, но без доверенности не подписывает (S-8) */
export const ROMASHKA_ACCOUNTANT: DemoAccount = {
  login: 'accountant@romashka.test',
  caption: 'Бухгалтер ООО «Ромашка» и ИП Иванова',
  shortName: 'Ольга Кузнецова',
}

export const IVANOV: DemoAccount = {
  login: 'ivanov@ip.test',
  caption: 'ИП Иванов',
  shortName: 'Иван Иванов',
}

/** Директор «Вектора» по кабинету; в ЕГРЮЛ руководитель другой (S-3) */
export const VECTOR_DIRECTOR: DemoAccount = {
  login: 'petrov@vector.test',
  caption: 'Директор ООО «Вектор» (полномочие не подтверждено)',
  shortName: 'Пётр Петров',
}

export const PROGRESS_OWNER: DemoAccount = {
  login: 'owner@progress.test',
  caption: 'Директор ООО «Прогресс»',
  shortName: 'Павел Прогрессов',
}

export const SBOY_OWNER: DemoAccount = {
  login: 'owner@sboy.test',
  caption: 'Директор ООО «Сбой»',
  shortName: 'Семён Сбоев',
}

/** Учредитель и директор стартапа «Старт»: ветка стартапа (S-9, S-10) */
export const START_OWNER: DemoAccount = {
  login: 'owner@start.test',
  caption: 'Учредитель и директор ООО «Старт» (стартап)',
  shortName: 'Степан Стартов',
}

/** Андеррайтер стенда: решает задачи в рабочем месте /admin и заявки, которые клиент сам закрыть не может (support/api.ts) */
export const UNDERWRITER: DemoAccount = {
  login: 'underwriter@bank.test',
  caption: 'Андеррайтер',
  shortName: 'Андрей Андеррайтеров',
}

/** Администратор: всё рабочее место, включая пользователей и роли */
export const ADMIN: DemoAccount = {
  login: 'admin@example.com',
  caption: 'Администратор',
  shortName: 'Admin Admin',
}

/** Пароль всех демо-учёток (DEMO_PASSWORD в .env стенда): нужен для входа по паролю и подписи договора */
export const DEMO_PASSWORD = process.env.E2E_DEMO_PASSWORD ?? 'Demo-2026!'
