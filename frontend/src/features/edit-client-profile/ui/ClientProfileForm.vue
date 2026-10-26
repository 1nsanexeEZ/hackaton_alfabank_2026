<script setup lang="ts">
import { CircleCheck, Lock, MessageSquare, ShieldCheck } from 'lucide-vue-next'
import { computed, reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { customer } from '@/entities/customer'
import { ROUTE_PATH } from '@/shared/config'
import { errorMessage } from '@/shared/lib'
import { BaseButton, TextField } from '@/shared/ui'

/**
 * Профиль клиента. ФИО подтверждено банком по паспорту, должность руководителя — по ЕГРЮЛ: по ним
 * банк сверяет руководителя с реестром и указывает подписанта в договоре, поэтому клиент их не меняет
 * (нет права profile.update_name) — блок только для чтения, без «Сохранить». Вход по email или телефону
 * тоже меняет банк.
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

const fullName = computed(() => [form.lastName, form.firstName, form.middleName].filter(Boolean).join(' ') || '—')

/** Строки блока только для чтения. Откуда банк взял ФИО и должность, клиенту не показываем — только зачем контакты */
const readonlyRows = computed(() =>
  [
    { label: 'ФИО', value: fullName.value, hint: '' },
    { label: 'Должность', value: form.position || '—', hint: '' },
    me?.email ? { label: 'Email', value: me.email, hint: '' } : null,
    me?.phone ? { label: 'Телефон', value: me.phone, hint: '' } : null,
  ].filter((row): row is { label: string; value: string; hint: string } => row !== null),
)

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
  <!-- Клиент: всё подтверждено банком — только чтение, вместо «Сохранить» — куда обратиться -->
  <section v-if="nameLocked" class="space-y-4" aria-labelledby="client-identity-title">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 id="client-identity-title" class="sr-only">Данные для договора</h3>
      <span class="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-2.5 py-1 text-xs font-semibold text-success">
        <ShieldCheck class="size-3.5" aria-hidden="true" />
        Подтверждено банком
      </span>
    </div>

    <dl class="divide-y divide-line rounded-2xl bg-surface-soft px-4">
      <div v-for="row in readonlyRows" :key="row.label" class="grid grid-cols-[7rem_minmax(0,1fr)] items-center gap-x-3 gap-y-0.5 py-3 sm:grid-cols-[8.5rem_minmax(0,1fr)_auto]">
        <dt class="text-[0.8125rem] text-ink-secondary">{{ row.label }}</dt>
        <dd class="font-semibold break-words text-ink">{{ row.value }}</dd>
        <span v-if="row.hint" class="col-start-2 justify-self-start text-xs text-ink-secondary sm:col-start-auto sm:justify-self-end">
          {{ row.hint }}
        </span>
      </div>
    </dl>

    <div class="flex flex-col gap-3 rounded-2xl p-4 ring-1 ring-line sm:flex-row sm:items-center">
      <span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-surface text-ink-secondary" aria-hidden="true">
        <Lock class="size-4" />
      </span>
      <p class="flex-1 text-sm text-ink-secondary">
        Если данные указаны неверно или изменились — свяжитесь с банком, и сотрудник их обновит.
      </p>
      <RouterLink
        :to="ROUTE_PATH.support"
        class="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-xl bg-night px-4 text-sm font-bold text-white transition-colors hover:bg-night-elevated"
      >
        <MessageSquare class="size-4" aria-hidden="true" />
        Написать в банк
      </RouterLink>
    </div>
  </section>

  <!-- Сотрудник с правом правки своего ФИО -->
  <form v-else class="space-y-5" @submit.prevent="save">
    <div class="grid gap-4 sm:grid-cols-2">
      <TextField v-model="form.lastName" label="Фамилия" autocomplete="family-name" :maxlength="100" />
      <TextField v-model="form.firstName" label="Имя" autocomplete="given-name" :maxlength="100" />
      <TextField v-model="form.middleName" label="Отчество" autocomplete="additional-name" :maxlength="100" />
      <TextField v-model="form.position" label="Должность" autocomplete="organization-title" :maxlength="150" />
    </div>

    <p v-if="error" class="rounded-2xl bg-brand-soft p-3 text-sm text-brand" role="alert">{{ error }}</p>
    <div class="flex flex-wrap items-center gap-4">
      <BaseButton type="submit" :loading="saving">Сохранить</BaseButton>
      <p v-if="saved" class="flex items-center gap-2 text-sm text-success" role="status">
        <CircleCheck class="size-4" aria-hidden="true" />
        Сохранено
      </p>
    </div>
  </form>
</template>
