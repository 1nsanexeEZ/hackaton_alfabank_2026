import type { InnCheckInput, InnCheckVerdict } from '@/shared/api'

/**
 * Демо-ИНН стенда (docs/modules/clients.md, «Проверка по ИНН до заявки»): данные — из external-mocks,
 * «клиент» — компания есть в сиде бэкенда. Несовпадение видно только с переданными реквизитами.
 */
export const DEMO_CHECKS: readonly { label: string; outcome: InnCheckVerdict; input: InnCheckInput }[] = [
  { label: 'Ромашка — клиент, всё чисто', outcome: 'ok', input: { inn: '7701158817' } },
  { label: 'Должник — недоимка и приставы', outcome: 'warning', input: { inn: '7707177037' } },
  { label: 'Вектор — карточка расходится с реестром', outcome: 'warning', input: { inn: '7702987976' } },
  { label: 'Прогресс — КПП не тот', outcome: 'warning', input: { inn: '7704568152', kpp: '770101001' } },
  {
    label: 'ИНН Ромашки с реквизитами Вектора',
    outcome: 'fail',
    input: { inn: '7701158817', ogrn: '1037702309116', name: 'ООО «Вектор»' },
  },
  { label: 'Крах — банкрот', outcome: 'fail', input: { inn: '7707177012' } },
  { label: 'Закат — ликвидация', outcome: 'fail', input: { inn: '7703417070' } },
  { label: 'Адрес-Сити — массовый адрес', outcome: 'fail', input: { inn: '7707177020' } },
  { label: 'Мираж — недостоверные сведения', outcome: 'fail', input: { inn: '7707146039' } },
  { label: 'Номинал — массовый руководитель', outcome: 'fail', input: { inn: '7707146046' } },
  { label: 'Стоп-Трейд — стоп-лист банка', outcome: 'fail', input: { inn: '7707146053' } },
  { label: 'Нет в реестре', outcome: 'not_found', input: { inn: '7707177990' } },
  { label: 'Ошибка в контрольной цифре', outcome: 'fail', input: { inn: '7701158818' } },
]
