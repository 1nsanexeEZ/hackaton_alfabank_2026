<script setup lang="ts">
import { Pencil, Search, Trash2, UserPlus } from 'lucide-vue-next'
import { computed, ref } from 'vue'

import { roleTitle } from '@/entities/role'
import { displayName, useSession } from '@/entities/session'
import { AccountFormModal, DeleteAccountModal } from '@/features/manage-account'
import { identityApi, type AccountDto } from '@/shared/api'
import { formatDate, useAsyncData } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton, PanelCard, ToggleSwitch } from '@/shared/ui'
import { AdminPageHeader } from '@/widgets/admin-layout'

const { can, me } = useSession()

const accounts = useAsyncData(() => identityApi.listAllAccounts())
// Список ролей нужен для формы; без права roles.read берём роли из уже загруженных аккаунтов
const roles = useAsyncData(() => (can('roles.read') ? identityApi.listRoles() : Promise.resolve([])))

const roleOptions = computed(() => {
  if (roles.data.value?.length) return roles.data.value
  const unique = new Map((accounts.data.value ?? []).map((account) => [account.role.id, account.role]))
  return [...unique.values()]
})

const search = ref('')
const showDeleted = ref(false)

const visible = computed(() => {
  const query = search.value.trim().toLowerCase()
  return (accounts.data.value ?? []).filter((account) => {
    if (!showDeleted.value && account.deleted_at) return false
    if (!query) return true
    return `${displayName(account)} ${account.email ?? ''} ${account.phone ?? ''} ${roleTitle(account.role.name)}`
      .toLowerCase()
      .includes(query)
  })
})

const editing = ref<AccountDto | null>(null)
const isFormOpen = ref(false)
const deleting = ref<AccountDto | null>(null)
const isDeleteOpen = ref(false)

function openCreate() {
  editing.value = null
  isFormOpen.value = true
}

function openEdit(account: AccountDto) {
  editing.value = account
  isFormOpen.value = true
}

function openDelete(account: AccountDto) {
  deleting.value = account
  isDeleteOpen.value = true
}

function onSaved(saved: AccountDto) {
  const list = accounts.data.value ?? []
  accounts.data.value = list.some((item) => item.id === saved.id)
    ? list.map((item) => (item.id === saved.id ? saved : item))
    : [...list, saved]
}

function onDeleted(id: string) {
  accounts.data.value = (accounts.data.value ?? []).map((item) =>
    item.id === id ? { ...item, deleted_at: new Date().toISOString() } : item,
  )
}
</script>

<template>
  <AdminPageHeader title="Пользователи" description="Сотрудники банка и клиенты с доступом в кабинет">
    <template v-if="can('accounts.create')" #actions>
      <BaseButton size="s" @click="openCreate">
        <UserPlus class="size-4" aria-hidden="true" />
        Добавить
      </BaseButton>
    </template>
  </AdminPageHeader>

  <PanelCard flush>
    <div class="flex flex-col gap-3 border-b border-line p-4 sm:flex-row sm:items-center sm:justify-between">
      <label class="relative block sm:w-80">
        <span class="sr-only">Поиск</span>
        <Search class="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-ink-secondary" aria-hidden="true" />
        <input
          v-model="search"
          type="search"
          placeholder="Имя, email, телефон или роль"
          class="h-11 w-full rounded-lg bg-surface pr-4 pl-10 text-sm text-ink outline-none placeholder:text-ink-muted focus:bg-white focus:ring-2 focus:ring-ink/20"
        />
      </label>
      <ToggleSwitch v-model="showDeleted" label="Показывать удалённых" class="sm:w-60" />
    </div>

    <AsyncState
      :loading="accounts.loading.value"
      :error="accounts.error.value"
      :empty="!visible.length"
      empty-text="Никого не нашли"
      @retry="accounts.reload"
    >
      <ul class="divide-y divide-line">
        <li
          v-for="account in visible"
          :key="account.id"
          class="flex flex-wrap items-center gap-x-4 gap-y-2 px-5 py-3.5 lg:grid lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1.3fr)_11rem_9rem_5rem]"
          :class="account.deleted_at && 'opacity-60'"
        >
          <div class="min-w-0 flex-1 basis-56">
            <p class="truncate font-medium text-ink">
              {{ displayName(account) }}
              <span v-if="account.id === me?.id" class="text-sm font-normal text-ink-secondary">· это вы</span>
            </p>
            <p class="truncate text-sm text-ink-secondary">{{ account.profile?.position ?? '—' }}</p>
          </div>
          <div class="min-w-0 basis-56 text-sm">
            <p class="truncate text-ink">{{ account.email ?? '—' }}</p>
            <p class="truncate text-ink-secondary">{{ account.phone ?? '' }}</p>
          </div>
          <div class="basis-40">
            <BaseBadge :tone="account.role.name === 'admin' ? 'brand' : account.role.name === 'client' ? 'neutral' : 'info'">
              {{ roleTitle(account.role.name) }}
            </BaseBadge>
          </div>
          <p class="basis-36 text-sm text-ink-secondary">
            {{ account.deleted_at ? `Удалён ${formatDate(account.deleted_at)}` : `С ${formatDate(account.created_at)}` }}
          </p>
          <div class="ml-auto flex gap-1">
            <button
              v-if="can('accounts.update') && !account.deleted_at"
              type="button"
              class="flex size-9 items-center justify-center rounded-lg text-ink-secondary transition-colors hover:bg-surface hover:text-ink"
              :aria-label="`Изменить: ${displayName(account)}`"
              @click="openEdit(account)"
            >
              <Pencil class="size-4" aria-hidden="true" />
            </button>
            <button
              v-if="can('accounts.delete') && !account.deleted_at && account.id !== me?.id"
              type="button"
              class="flex size-9 items-center justify-center rounded-lg text-ink-secondary transition-colors hover:bg-brand-soft hover:text-brand"
              :aria-label="`Удалить: ${displayName(account)}`"
              @click="openDelete(account)"
            >
              <Trash2 class="size-4" aria-hidden="true" />
            </button>
          </div>
        </li>
      </ul>
    </AsyncState>
  </PanelCard>

  <AccountFormModal v-model:open="isFormOpen" :account="editing" :roles="roleOptions" @saved="onSaved" />
  <DeleteAccountModal
    v-model:open="isDeleteOpen"
    :account="deleting"
    :name="deleting ? displayName(deleting) : ''"
    @deleted="onDeleted"
  />
</template>
