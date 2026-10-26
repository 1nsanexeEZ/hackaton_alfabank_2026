import { describe, expect, it } from 'vitest'
import { nextTick } from 'vue'

import { MODULES, packRows, useBoardLayout, type BoardModule } from './layout'
import { STATUS, STATUS_GROUPS, trackProgress } from './status'

const module = (id: BoardModule['id'], span: BoardModule['span']): BoardModule => ({ id, title: id, description: '', span })
const spans = (modules: BoardModule[]) => packRows(modules).map((row) => `${row.module.id}:${row.span}`)

describe('packRows — модули обзора по рядам без дыр', () => {
  it('раскладка по умолчанию сходится по три колонки', () => {
    const visible = MODULES.filter((item) => !item.optional)
    expect(spans(visible)).toEqual(['kpi:3', 'flow:2', 'queue:1', 'funnel:2', 'decided:1', 'feed:3'])
  })

  it('не влезающий модуль переносится, предыдущий растягивается до конца ряда', () => {
    expect(spans([module('queue', 1), module('flow', 2), module('funnel', 2)])).toEqual(['queue:1', 'flow:2', 'funnel:3'])
    expect(spans([module('flow', 2), module('funnel', 2)])).toEqual(['flow:3', 'funnel:3'])
  })

  it('последний модуль занимает остаток ряда', () => {
    expect(spans([module('queue', 1)])).toEqual(['queue:3'])
    expect(spans([])).toEqual([])
  })
})

describe('useBoardLayout — настройка панели', () => {
  // localStorage в node нет: раскладка не сохраняется, но работает
  it('дополнительные модули скрыты, пока сотрудник их не включит', () => {
    const layout = useBoardLayout()
    expect(layout.visible.value.map((item) => item.id)).toEqual(['kpi', 'flow', 'queue', 'funnel', 'decided', 'feed'])
    layout.toggle('grades')
    expect(layout.visible.value.map((item) => item.id)).toContain('grades')
    layout.toggle('kpi')
    expect(layout.visible.value.map((item) => item.id)).not.toContain('kpi')
  })

  it('модуль двигается на шаг, за край не уходит, сброс возвращает порядок', async () => {
    const layout = useBoardLayout()
    layout.move('queue', -1)
    expect(layout.modules.value.slice(0, 3).map((item) => item.id)).toEqual(['kpi', 'queue', 'flow'])
    layout.move('kpi', -1)
    expect(layout.modules.value[0]?.id).toBe('kpi')
    layout.reset()
    await nextTick()
    expect(layout.modules.value.map((item) => item.id)).toEqual(MODULES.map((item) => item.id))
    expect(layout.hidden.value).toEqual(MODULES.filter((item) => item.optional).map((item) => item.id))
  })
})

describe('статусы заявок в рабочем месте', () => {
  it('каждый статус бэкенда входит ровно в одну группу «Где заявки сейчас»', () => {
    const grouped = STATUS_GROUPS.flatMap((group) => group.statuses)
    expect([...grouped].sort()).toEqual(Object.keys(STATUS).sort())
  })

  it('мини-трекер: подача, решение, подписание, выдача', () => {
    expect(trackProgress('draft')).toEqual({ done: 0, failed: false })
    expect(trackProgress('in_review')).toEqual({ done: 1, failed: false })
    expect(trackProgress('info_requested')).toEqual({ done: 1, failed: false })
    expect(trackProgress('offer_ready')).toEqual({ done: 2, failed: false })
    expect(trackProgress('signed')).toEqual({ done: 3, failed: false })
    expect(trackProgress('disbursed')).toEqual({ done: 4, failed: false })
    expect(trackProgress('rejected')).toEqual({ done: 2, failed: true })
    expect(trackProgress('cancelled')).toEqual({ done: 0, failed: true })
  })
})
