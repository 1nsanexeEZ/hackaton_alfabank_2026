import { describe, expect, it } from 'vitest'

import { MATRIX_ACTIONS, PERMISSION_GROUPS, PERMISSION_SECTIONS, POLICY_META, roleTitle } from './permissions'

describe('права ролей', () => {
  const all = [...PERMISSION_GROUPS.flatMap((group) => group.items), ...PERMISSION_SECTIONS.flatMap((section) => section.items)].map(
    (item) => item.permission,
  )

  it('каждое право в редакторе роли встречается один раз', () => {
    expect(new Set(all).size).toBe(all.length)
  })

  it('матрица: у каждого раздела четыре действия в порядке колонок', () => {
    for (const group of PERMISSION_GROUPS) {
      expect(group.items.map((item) => item.action)).toEqual([...MATRIX_ACTIONS])
      for (const item of group.items) expect(item.permission.startsWith(`${group.id}.`)).toBe(true)
    }
  })

  it('рабочее место андеррайтера: задачи, решения, модель и политика', () => {
    expect(all).toEqual(expect.arrayContaining(['backoffice.read', 'tasks.read', 'tasks.update', 'decisions.read', 'scoring.read', 'scoring.update']))
  })

  it('политики доступа применимы только к своим разделам', () => {
    expect(POLICY_META.own_only.appliesTo).toEqual(['requests', 'credits'])
    expect(POLICY_META.org_member.appliesTo).toEqual(['requests'])
  })

  it('системные роли — по-русски, новые — как есть', () => {
    expect(roleTitle('underwriter')).toBe('Андеррайтер')
    expect(roleTitle('admin')).toBe('Администратор')
    expect(roleTitle('collector')).toBe('collector')
  })
})
