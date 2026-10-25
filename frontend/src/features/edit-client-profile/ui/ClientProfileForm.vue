<script setup lang="ts">
import { CircleCheck, Lock, ShieldCheck } from 'lucide-vue-next'
import { computed, reactive, ref } from 'vue'

import { customer } from '@/entities/customer'
import { errorMessage } from '@/shared/lib'
import { BaseButton, TextField } from '@/shared/ui'

/**
 * Профиль клиента. ФИО подтверждено банком при открытии счёта: по нему банк сверяет руководителя
 * с ЕГРЮЛ и указывает подписанта в договоре, поэтому клиент его не меняет (нет права
 * profile.update_name) — только должность. Вход по email или телефону тоже меняет банк, не клиент.
 */
const me = customer.state.me
const form = reactive({
  lastName: me?.profile?.last_name ?? '',
  firstName: me?.profile?.first_name ?? '',
  middleName: me?.profile?.middle_name ?? '',
  position: me?.profile?.position ?? '',
})

const nameLocked = computed(
  () => !me || !(me.permissions.includes('admin') || me.permissions.includes('profile.update_name')),
)

const nameRows = computed(() => [
  { label: 'Фамилия', value: form.lastName },
  { label: 'Имя', value: form.firstName },
  { label: 'Отчество', value: form.middleName || '—' },
])

const saving = ref(false)
const saved = ref(false)
const error = ref<string | null>(null)

async function save() {
  saving.value = true
  saved.value = false
  error.value = null
  try {
    const position = form.position.trim() || null
    await customer.updateProfile(
      nameLocked.value
        ? { position }
        : {
            last_name: form.lastName.trim() || null,
            first_name: form.firstName.trim() || null,
            middle_name: form.middleName.trim() || null,
            position,
          },
    )
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
    <section v-if="nameLocked" class="space-y-3 rounded-2xl bg-surface-soft p-4" aria-labelledby="client-identity-title">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <h3 id="client-identity-title" class="text-base font-bold text-ink">ФИО</h3>
        <span class="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-2.5 py-1 text-xs font-semibold text-success">
          <ShieldCheck class="size-3.5" aria-hidden="true" />
          Подтверждено банком
        </span>
      </div>
      <dl class="divide-y divide-line rounded-xl bg-white px-3.5">
        <div v-for="row in nameRows" :key="row.label" class="flex items-center gap-3 py-2.5">
          <div class="min-w-0 flex-1">
            <dt class="text-xs text-ink-secondary">{{ row.label }}</dt>
            <dd class="font-medium text-ink">{{ row.value }}</dd>
          </div>
          <Lock class="size-4 shrink-0 text-ink-secondary" aria-label="Нельзя изменить" role="img" />
        </div>
      </dl>
      <p class="text-sm text-ink-secondary">
        ФИО подтверждено по паспорту при открытии счёта — по нему банк сверяет руководителя с ЕГРЮЛ и указывает
        подписанта в договоре. Сменили паспорт — обратитесь в банк, данные обновит сотрудник.
      </p>
    </section>

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
      <template v-if="!nameLocked">
        <TextField v-model="form.lastName" label="Фамилия" autocomplete="family-name" :maxlength="100" />
        <TextField v-model="form.firstName" label="Имя" autocomplete="given-name" :maxlength="100" />
        <TextField v-model="form.middleName" label="Отчество" autocomplete="additional-name" :maxlength="100" />
      </template>
      <TextField
        v-model="form.position"
        label="Должность"
        autocomplete="organization-title"
        :maxlength="150"
        hint="Её видят сотрудники банка в ваших заявках. В договоре роль подписанта — по ЕГРЮЛ или доверенности"
        :class="nameLocked && 'sm:col-span-2'"
      />
    </div>

    <p v-if="error" class="rounded-2xl bg-brand-soft p-3 text-sm text-brand" role="alert">{{ error }}</p>
    <p v-else-if="saved" class="flex items-center gap-2 text-sm text-success" role="status">
      <CircleCheck class="size-4" aria-hidden="true" />
      Сохранено
    </p>

    <BaseButton type="submit" :loading="saving">Сохранить</BaseButton>
  </form>
</template>
