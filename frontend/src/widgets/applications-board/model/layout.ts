import { computed, ref, watch } from 'vue'

import { readStorage, writeStorage } from '@/shared/lib'

export type ModuleId = 'kpi' | 'flow' | 'decided' | 'funnel' | 'statuses' | 'queue' | 'products' | 'amounts' | 'grades' | 'feed'

export interface BoardModule {
  id: ModuleId
  title: string
  description: string
  /** Сколько колонок сетки занимает на широком экране: из трёх */
  span: 1 | 2 | 3
}

/** Модули панели в порядке по умолчанию */
export const MODULES: readonly BoardModule[] = [
  { id: 'kpi', title: 'Ключевые показатели', description: 'Заявки, сумма запросов, одобрение и скорость решения', span: 3 },
  { id: 'flow', title: 'Поток решений по дням', description: 'Одобрения, встречные предложения и отказы за период', span: 2 },
  { id: 'decided', title: 'Куда уходят заявки', description: 'Сразу решила автоматика или передала специалисту', span: 1 },
  { id: 'funnel', title: 'Воронка заявок', description: 'Сколько заявок дошли до каждого этапа', span: 2 },
  { id: 'statuses', title: 'Где заявки сейчас', description: 'Группы статусов', span: 1 },
  { id: 'queue', title: 'Очередь специалиста', description: 'Открытые задачи и срок по SLA', span: 1 },
  { id: 'products', title: 'Продукты', description: 'Заявки и сумма запросов по продуктам', span: 1 },
  { id: 'amounts', title: 'Суммы запросов', description: 'Сколько заявок в каждом диапазоне', span: 1 },
  { id: 'feed', title: 'Последние заявки', description: 'Карточки с этапом, как их видит клиент', span: 2 },
  { id: 'grades', title: 'Грейды скоринга', description: 'Оценка PD-модели по последним поданным', span: 1 },
]

const STORAGE_KEY = 'admin.applications-board.v2'

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
  const known = (stored?.order ?? []).filter(isModule)
  const order = ref<ModuleId[]>([...known, ...defaults.filter((id) => !known.includes(id))])
  const hidden = ref<ModuleId[]>((stored?.hidden ?? []).filter(isModule))

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
    hidden.value = []
  }

  return { modules, visible, hidden, toggle, move, reset }
}
