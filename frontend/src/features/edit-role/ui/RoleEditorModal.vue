<script setup lang="ts">
import { Check } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'

import { MATRIX_ACTIONS, PERMISSION_GROUPS, POLICY_META } from '@/entities/role'
import { identityApi, type Permission, type Policy, type PolicyMap, type RoleDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'
import { BaseButton, BaseModal, TextField, ToggleSwitch } from '@/shared/ui'

/**
 * Редактор роли: матрица «раздел × действие» и политики к правам.
 * Политики можно задать только для включённых прав — так же проверяет бэкенд.
 */
const props = defineProps<{ role: RoleDto | null }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ saved: [role: RoleDto] }>()

const POLICIES = Object.keys(POLICY_META) as Policy[]

const form = reactive({
  name: '',
  description: '',
  permissions: new Set<Permission>(),
  policies: {} as PolicyMap,
})
const nameError = ref<string | undefined>()
const formError = ref<string | null>(null)
const pending = ref(false)

watch(open, (isOpen) => {
  if (!isOpen) return
  form.name = props.role?.name ?? ''
  form.description = props.role?.description ?? ''
  form.permissions = new Set(props.role?.permissions ?? ['profile.update'])
  form.policies = structuredClone(props.role?.policies ?? {})
  nameError.value = undefined
  formError.value = null
})

const isAdmin = computed({
  get: () => form.permissions.has('admin'),
  set: (value) => toggle('admin', value),
})

const canEditProfile = computed({
  get: () => form.permissions.has('profile.update'),
  set: (value) => toggle('profile.update', value),
})

// Своё ФИО — отдельное право: клиентам его не дают, их ФИО подтверждено банком
const canEditName = computed({
  get: () => form.permissions.has('profile.update_name'),
  set: (value) => toggle('profile.update_name', value),
})

function toggle(permission: Permission, value = !form.permissions.has(permission)) {
  const next = new Set(form.permissions)
  if (value) next.add(permission)
  else {
    next.delete(permission)
    delete form.policies[permission]
  }
  form.permissions = next
}

function hasPolicy(permission: Permission, policy: Policy) {
  return form.policies[permission]?.includes(policy) ?? false
}

function togglePolicy(permission: Permission, policy: Policy) {
  const current = form.policies[permission] ?? []
  const next = current.includes(policy) ? current.filter((item) => item !== policy) : [...current, policy]
  if (next.length) form.policies[permission] = next
  else delete form.policies[permission]
}

async function submit() {
  formError.value = null
  nameError.value = /^[a-z][a-z0-9_-]{1,63}$/.test(form.name.trim())
    ? undefined
    : 'Латиница в нижнем регистре, цифры, «-» и «_», например risk_manager'
  if (nameError.value) return
  pending.value = true
  const data = {
    name: form.name.trim(),
    description: form.description.trim(),
    permissions: [...form.permissions],
    policies: form.policies,
  }
  try {
    const saved = props.role ? await identityApi.updateRole(props.role.id, data) : await identityApi.createRole(data)
    emit('saved', saved)
    open.value = false
  } catch (caught) {
    formError.value = errorMessage(caught)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <BaseModal
    v-model:open="open"
    :title="role ? 'Изменить роль' : 'Новая роль'"
    description="Пользователи получат новые права со следующим входом — токен живёт до 30 минут"
    wide
  >
    <form id="role-form" class="space-y-5" novalidate @submit.prevent="submit">
      <div class="grid gap-3 sm:grid-cols-2">
        <TextField v-model="form.name" label="Системное имя" dense :error="nameError" placeholder="risk_manager" />
        <TextField v-model="form.description" label="Описание" dense placeholder="Что делает роль" />
      </div>

      <div class="space-y-3 rounded-xl bg-surface-soft p-4">
        <ToggleSwitch v-model="isAdmin" label="Полный доступ" description="Право admin обходит все остальные права и политики" />
        <ToggleSwitch v-model="canEditProfile" label="Правка своего профиля" />
        <ToggleSwitch
          v-model="canEditName"
          label="Правка своего ФИО"
          description="Сотрудникам. Клиентам не давайте: их ФИО подтверждено банком, по нему сверяется руководитель с ЕГРЮЛ"
        />
      </div>

      <div class="overflow-x-auto" :class="isAdmin && 'pointer-events-none opacity-40'">
        <table class="w-full min-w-[36rem] text-sm">
          <thead class="text-xs text-ink-secondary">
            <tr>
              <th scope="col" class="pb-2 text-left font-medium">Раздел</th>
              <th v-for="action in MATRIX_ACTIONS" :key="action" scope="col" class="pb-2 font-medium">{{ action }}</th>
            </tr>
          </thead>
          <tbody>
            <template v-for="group in PERMISSION_GROUPS" :key="group.id">
              <tr class="border-t border-line">
                <th scope="row" class="py-2.5 text-left font-medium text-ink">{{ group.title }}</th>
                <td v-for="item in group.items" :key="item.permission" class="py-2.5 text-center">
                  <button
                    type="button"
                    role="checkbox"
                    :aria-checked="form.permissions.has(item.permission)"
                    :aria-label="`${group.title}: ${item.action}`"
                    :class="[
                      'inline-flex size-7 items-center justify-center rounded-md border-2 transition',
                      form.permissions.has(item.permission) ? 'border-brand bg-brand text-white' : 'border-ink-muted hover:border-ink-secondary',
                    ]"
                    @click="toggle(item.permission)"
                  >
                    <Check v-if="form.permissions.has(item.permission)" class="size-4" :stroke-width="3" aria-hidden="true" />
                  </button>
                </td>
              </tr>
              <tr v-if="group.items.some((item) => form.permissions.has(item.permission))">
                <td colspan="5" class="pb-3">
                  <div class="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg bg-surface-soft px-3 py-2 text-xs">
                    <span class="text-ink-secondary">Политики к просмотру:</span>
                    <template v-for="policy in POLICIES" :key="policy">
                      <label
                        v-if="POLICY_META[policy].appliesTo.includes(group.id) && form.permissions.has(group.items[0]!.permission)"
                        class="flex cursor-pointer items-center gap-1.5 text-ink"
                        :title="POLICY_META[policy].description"
                      >
                        <input
                          type="checkbox"
                          class="size-4 accent-brand"
                          :checked="hasPolicy(group.items[0]!.permission, policy)"
                          @change="togglePolicy(group.items[0]!.permission, policy)"
                        />
                        {{ POLICY_META[policy].label }}
                      </label>
                    </template>
                    <span v-if="!form.permissions.has(group.items[0]!.permission)" class="text-ink-muted">включите просмотр</span>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </form>
    <p v-if="formError" class="mt-4 rounded-xl bg-brand-soft px-4 py-3 text-sm text-brand" role="alert">{{ formError }}</p>
    <template #footer>
      <BaseButton variant="secondary" @click="open = false">Отмена</BaseButton>
      <BaseButton type="submit" form="role-form" :loading="pending">{{ role ? 'Сохранить' : 'Создать' }}</BaseButton>
    </template>
  </BaseModal>
</template>
