<script setup lang="ts">
import { Check, Minus, Pencil, Plus, Trash2 } from 'lucide-vue-next'
import { computed, ref } from 'vue'

import { MATRIX_ACTIONS, PERMISSION_GROUPS, PERMISSION_SECTIONS, POLICY_META, roleTitle } from '@/entities/role'
import { useSession } from '@/entities/session'
import { RoleEditorModal } from '@/features/edit-role'
import { identityApi, type RoleDto } from '@/shared/api'
import { errorMessage, pluralize, useAsyncData } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton, BaseModal, PanelCard } from '@/shared/ui'
import { AdminPageHeader } from '@/widgets/admin-layout'

const { can } = useSession()

const roles = useAsyncData(() => identityApi.listRoles())
const accounts = useAsyncData(() => (can('accounts.read') ? identityApi.listAccounts() : Promise.resolve([])))

const usage = computed(() => {
  const counts = new Map<string, number>()
  for (const account of accounts.data.value ?? []) {
    if (!account.deleted_at) counts.set(account.role.id, (counts.get(account.role.id) ?? 0) + 1)
  }
  return counts
})

const has = (role: RoleDto, permission: string) =>
  role.permissions.includes('admin') || role.permissions.includes(permission as RoleDto['permissions'][number])

const editing = ref<RoleDto | null>(null)
const isEditorOpen = ref(false)

function openEditor(role: RoleDto | null) {
  editing.value = role
  isEditorOpen.value = true
}

function onSaved(saved: RoleDto) {
  const list = roles.data.value ?? []
  roles.data.value = list.some((item) => item.id === saved.id)
    ? list.map((item) => (item.id === saved.id ? saved : item))
    : [...list, saved]
}

const deleting = ref<RoleDto | null>(null)
const isDeleteOpen = ref(false)
const deletePending = ref(false)
const deleteError = ref<string | null>(null)

function openDelete(role: RoleDto) {
  deleting.value = role
  deleteError.value = null
  isDeleteOpen.value = true
}

async function confirmDelete() {
  if (!deleting.value) return
  deletePending.value = true
  deleteError.value = null
  try {
    await identityApi.deleteRole(deleting.value.id)
    roles.data.value = (roles.data.value ?? []).filter((item) => item.id !== deleting.value?.id)
    isDeleteOpen.value = false
  } catch (caught) {
    deleteError.value = errorMessage(caught)
  } finally {
    deletePending.value = false
  }
}
</script>

<template>
  <AdminPageHeader title="Роли и права" description="RBAC: права на разделы; ABAC: политики сужают, какие записи видны">
    <template v-if="can('roles.create')" #actions>
      <BaseButton size="s" @click="openEditor(null)">
        <Plus class="size-4" aria-hidden="true" />
        Новая роль
      </BaseButton>
    </template>
  </AdminPageHeader>

  <AsyncState :loading="roles.loading.value" :error="roles.error.value" @retry="roles.reload">
    <div class="grid gap-6 xl:grid-cols-2">
      <PanelCard v-for="role in roles.data.value ?? []" :key="role.id" :title="roleTitle(role.name)" :description="role.description || undefined">
        <template #actions>
          <BaseBadge v-if="can('accounts.read')">
            {{ usage.get(role.id) ?? 0 }} {{ pluralize(usage.get(role.id) ?? 0, ['пользователь', 'пользователя', 'пользователей']) }}
          </BaseBadge>
          <button
            v-if="can('roles.update')"
            type="button"
            class="flex size-8 items-center justify-center rounded-lg text-ink-secondary transition-colors hover:bg-surface hover:text-ink"
            :aria-label="`Изменить роль ${roleTitle(role.name)}`"
            @click="openEditor(role)"
          >
            <Pencil class="size-4" aria-hidden="true" />
          </button>
          <button
            v-if="can('roles.delete')"
            type="button"
            class="flex size-8 items-center justify-center rounded-lg text-ink-secondary transition-colors hover:bg-brand-soft hover:text-brand"
            :aria-label="`Удалить роль ${roleTitle(role.name)}`"
            @click="openDelete(role)"
          >
            <Trash2 class="size-4" aria-hidden="true" />
          </button>
        </template>

        <p v-if="role.permissions.includes('admin')" class="mb-3 rounded-lg bg-brand-soft px-3 py-2 text-sm text-brand">
          Полный доступ: право admin обходит остальные права и политики
        </p>
        <table class="w-full text-sm">
          <caption class="sr-only">Права роли {{ roleTitle(role.name) }}</caption>
          <thead class="text-xs text-ink-secondary">
            <tr>
              <th scope="col" class="pb-2 text-left font-medium">Раздел</th>
              <th v-for="action in MATRIX_ACTIONS" :key="action" scope="col" class="w-[4.5rem] px-1 pb-2 text-[11px] font-medium">{{ action }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="group in PERMISSION_GROUPS" :key="group.id" class="border-t border-line">
              <th scope="row" class="py-2 text-left font-normal text-ink">
                {{ group.title }}
                <span
                  v-for="policy in role.policies[group.items[0]!.permission] ?? []"
                  :key="policy"
                  class="ml-1 rounded bg-surface px-1.5 py-0.5 text-[11px] text-ink-secondary"
                >
                  {{ POLICY_META[policy].label.toLowerCase() }}
                </span>
              </th>
              <td v-for="item in group.items" :key="item.permission" class="py-2 text-center">
                <Check v-if="has(role, item.permission)" class="mx-auto size-4 text-success" :stroke-width="3" aria-label="есть" />
                <Minus v-else class="mx-auto size-4 text-ink-muted" aria-label="нет" />
              </td>
            </tr>
          </tbody>
        </table>
        <ul v-if="!role.permissions.includes('admin')" class="mt-3 flex flex-wrap gap-1.5">
          <template v-for="section in PERMISSION_SECTIONS" :key="section.title">
            <li v-for="item in section.items.filter((entry) => has(role, entry.permission))" :key="item.permission">
              <BaseBadge tone="success" :title="section.title">{{ item.label }}</BaseBadge>
            </li>
          </template>
        </ul>
        <p class="mt-3 text-xs text-ink-secondary">Системное имя: <code>{{ role.name }}</code></p>
      </PanelCard>
    </div>
  </AsyncState>

  <RoleEditorModal v-model:open="isEditorOpen" :role="editing" @saved="onSaved" />

  <BaseModal v-model:open="isDeleteOpen" title="Удалить роль?">
    <p class="text-sm text-ink">
      Роль <b class="font-semibold">{{ deleting ? roleTitle(deleting.name) : '' }}</b> удалится насовсем. Если она назначена
      пользователям, сначала смените им роль.
    </p>
    <p v-if="deleteError" class="mt-3 text-sm text-brand" role="alert">{{ deleteError }}</p>
    <template #footer>
      <BaseButton variant="secondary" @click="isDeleteOpen = false">Отмена</BaseButton>
      <BaseButton :loading="deletePending" @click="confirmDelete">Удалить</BaseButton>
    </template>
  </BaseModal>
</template>
