<script setup lang="ts">
import { CircleCheck } from 'lucide-vue-next'
import { reactive, ref } from 'vue'

import { customer } from '@/entities/customer'
import { errorMessage } from '@/shared/lib'
import { BaseButton, TextField } from '@/shared/ui'

/** Профиль клиента: ФИО и должность. Вход по email или телефону — их меняет банк, не клиент */
const me = customer.state.me
const form = reactive({
  lastName: me?.profile?.last_name ?? '',
  firstName: me?.profile?.first_name ?? '',
  middleName: me?.profile?.middle_name ?? '',
  position: me?.profile?.position ?? '',
})

const saving = ref(false)
const saved = ref(false)
const error = ref<string | null>(null)

async function save() {
  saving.value = true
  saved.value = false
  error.value = null
  try {
    await customer.updateProfile({
      last_name: form.lastName.trim() || null,
      first_name: form.firstName.trim() || null,
      middle_name: form.middleName.trim() || null,
      position: form.position.trim() || null,
    })
    saved.value = true
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <form class="space-y-5" @submit.prevent="save">
    <dl class="rounded-2xl bg-surface-soft px-4 py-3 text-sm">
      <div v-if="me?.email" class="flex justify-between gap-4 py-1">
        <dt class="text-ink-secondary">Email</dt>
        <dd class="font-medium text-ink">{{ me.email }}</dd>
      </div>
      <div v-if="me?.phone" class="flex justify-between gap-4 py-1">
        <dt class="text-ink-secondary">Телефон</dt>
        <dd class="font-medium text-ink">{{ me.phone }}</dd>
      </div>
    </dl>

    <div class="grid gap-4 sm:grid-cols-2">
      <TextField v-model="form.lastName" label="Фамилия" autocomplete="family-name" :maxlength="100" />
      <TextField v-model="form.firstName" label="Имя" autocomplete="given-name" :maxlength="100" />
      <TextField v-model="form.middleName" label="Отчество" autocomplete="additional-name" :maxlength="100" />
      <TextField v-model="form.position" label="Должность" autocomplete="organization-title" :maxlength="200" />
    </div>

    <p v-if="error" class="rounded-2xl bg-brand-soft p-3 text-sm text-brand" role="alert">{{ error }}</p>
    <p v-else-if="saved" class="flex items-center gap-2 text-sm text-success" role="status">
      <CircleCheck class="size-4" aria-hidden="true" />
      Сохранено
    </p>

    <BaseButton type="submit" :loading="saving">Сохранить</BaseButton>
  </form>
</template>
