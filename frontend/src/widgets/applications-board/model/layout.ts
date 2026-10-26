import { computed, ref, watch } from 'vue'

import { readStorage, writeStorage } from '@/shared/lib'

export type ModuleId = 'kpi' | 'flow' | 'decided' | 'funnel' | 'statuses' | 'queue' | 'products' | 'amounts' | 'grades' | 'feed'

export interface BoardModule {
  id: ModuleId
  title: string
  description: string
  /** Сколько колонок сетки занимает на широком экране: из трёх */
  span: 1 | 2 | 3
  /** Без своей карточки: плитки встают прямо на страницу */
  bare?: boolean
  /** Дополнительный: скрыт, пока сотрудник не включит его в «Настроить панель» */
  optional?: boolean
}

/**
 * Модули панели в порядке по умолчанию. Главное — показатели, решения по дням рядом с очередью, воронка
 * рядом с долей автоматики и последние заявки: ряды сходятся по три колонки без дыр. Остальное — по желанию.
 */
export const MODULES: readonly BoardModule[] = [
  { id: 'kpi', title: 'Ключевые показатели', description: 'Заявки, одобрение и скорость решения', span: 3, bare: true },
  { id: 'flow', title: 'Решения по дням', description: 'Одобрения, встречные предложения и отказы за период', span: 2 },
  { id: 'queue', title: 'Очередь специалиста', description: 'Открытые задачи и срок по SLA', span: 1 },
  { id: 'funnel', title: 'Воронка заявок', description: 'Сколько заявок дошли до каждого этапа', span: 2 },
  { id: 'decided', title: 'Кто решает', description: 'Сразу автоматика или специалист', span: 1 },
  { id: 'feed', title: 'Последние заявки', description: 'Что менялось недавно', span: 3 },
  { id: 'statuses', title: 'Где заявки сейчас', description: 'Группы статусов', span: 1, optional: true },
  { id: 'products', title: 'Продукты', description: 'Заявки и сумма запросов по продуктам', span: 1, optional: true },
  { id: 'amounts', title: 'Суммы запросов', description: 'Сколько заявок в каждом диапазоне', span: 1, optional: true },
  { id: 'grades', title: 'Грейды скоринга', description: 'Оценка PD-модели по последним поданным', span: 1, optional: true },
]

/** Ширина колонки сетки модулей на широком экране */
const COLUMNS = 3

/**
 * Модули по рядам без дыр: модуль, который не влезает в остаток ряда, переносится, а предыдущий
 * растягивается до конца ряда; последний — тоже до конца. Возвращает ширину каждого модуля в колонках.
 */
export function packRows(modules: readonly BoardModule[]): { module: BoardModule; span: 1 | 2 | 3 }[] {
  const rows: { module: BoardModule; span: number }[] = []
  let column = 0
  for (const module of modules) {
    const last = rows[rows.length - 1]
    if (column + module.span > COLUMNS && last) {
      last.span += COLUMNS - column
      column = 0
    }
    rows.push({ module, span: module.span })
    column = (column + module.span) % COLUMNS
  }
  const last = rows[rows.length - 1]
  if (column && last) last.span += COLUMNS - column
  return rows.map((row) => ({ module: row.module, span: row.span as 1 | 2 | 3 }))
}

/** v3 — новая раскладка по умолчанию: сохранённые раньше порядок и скрытые модули не подхватываем */
const STORAGE_KEY = 'admin.applications-board.v3'

interface StoredLayout {
  order: ModuleId[]
  hidden: ModuleId[]
}

const isModule = (id: string): id is ModuleId => MODULES.some((module) => module.id === id)

/**
 * Раскладка панели: порядок и скрытые модули. Запоминается в браузере сотрудника; новые модули,
 * которых не было в сохранённой раскладке, встают в конец.
 */
export function useBoardLayout() {
  const stored = readStorage<StoredLayout>(STORAGE_KEY)
  const defaults = MODULES.map((module) => module.id)
  const optional = MODULES.filter((module) => module.optional).map((module) => module.id)
  const known = (stored?.order ?? []).filter(isModule)
  const order = ref<ModuleId[]>([...known, ...defaults.filter((id) => !known.includes(id))])
  const hidden = ref<ModuleId[]>(stored ? stored.hidden.filter(isModule) : [...optional])

  watch([order, hidden], () => writeStorage(STORAGE_KEY, { order: order.value, hidden: hidden.value }), { deep: true })

  const modules = computed(() => order.value.map((id) => MODULES.find((module) => module.id === id)!))
  const visible = computed(() => modules.value.filter((module) => !hidden.value.includes(module.id)))

  function toggle(id: ModuleId) {
    hidden.value = hidden.value.includes(id) ? hidden.value.filter((item) => item !== id) : [...hidden.value, id]
  }

  function move(id: ModuleId, step: -1 | 1) {
    const index = order.value.indexOf(id)
    const target = index + step
    if (target < 0 || target >= order.value.length) return
    const next = [...order.value]
    next.splice(index, 1)
    next.splice(target, 0, id)
    order.value = next
  }

  function reset() {
    order.value = [...defaults]
    hidden.value = [...optional]
  }

  return { modules, visible, hidden, toggle, move, reset }
}
