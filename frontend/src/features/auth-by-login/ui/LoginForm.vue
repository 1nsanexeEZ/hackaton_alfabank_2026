<script setup lang="ts">
import { reactive, ref } from 'vue'

import { canEnterAdmin, session } from '@/entities/session'
import { API_MODE, MOCK_DEMO_ACCOUNTS, type MeDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'
import { BaseButton, TextField } from '@/shared/ui'

/** Вход сотрудника по email или телефону и паролю (POST /auth/login) */
const emit = defineEmits<{ success: [me: MeDto] }>()

const form = reactive({ login: '', password: '' })
const errors = reactive<{ login?: string; password?: string }>({})
const formError = ref<string | null>(null)
const pending = ref(false)

function validate(): boolean {
  errors.login = form.login.trim() ? undefined : 'Введите email или телефон'
  errors.password = form.password ? undefined : 'Введите пароль'
  return !errors.login && !errors.password
}

async function submit() {
  formError.value = null
  if (!validate()) return
  pending.value = true
  try {
    const me = await session.login(form.login.trim(), form.password)
    if (!canEnterAdmin(me)) {
      session.logout()
      formError.value = 'У этой учётной записи нет доступа к рабочему месту сотрудника'
      return
    }
    emit('success', me)
  } catch (error) {
    formError.value = errorMessage(error)
  } finally {
    pending.value = false
  }
}

function useDemo(account: (typeof MOCK_DEMO_ACCOUNTS)[number]) {
  form.login = account.login
  form.password = account.password
  errors.login = undefined
  errors.password = undefined
}
</script>

<template>
  <form class="space-y-4" novalidate @submit.prevent="submit">
    <TextField
      v-model="form.login"
      label="Email или телефон"
      type="email"
      autocomplete="username"
      placeholder="name@example.com"
      :error="errors.login"
    />
    <TextField
      v-model="form.password"
      label="Пароль"
      type="password"
      autocomplete="current-password"
      :error="errors.password"
    />
    <p v-if="formError" class="rounded-xl bg-brand-soft px-4 py-3 text-sm text-brand" role="alert">{{ formError }}</p>
    <BaseButton type="submit" size="l" block :loading="pending">Войти</BaseButton>

    <div v-if="API_MODE === 'mock'" class="rounded-2xl bg-surface-soft p-4">
      <p class="text-sm font-semibold text-ink">Демо-доступ</p>
      <p class="mt-0.5 text-xs text-ink-secondary">Нажмите, чтобы подставить логин и пароль</p>
      <div class="mt-3 grid gap-2">
        <button
          v-for="account in MOCK_DEMO_ACCOUNTS"
          :key="account.login"
          type="button"
          class="flex items-center justify-between gap-3 rounded-xl bg-white px-3 py-2.5 text-left text-sm ring-1 ring-line transition hover:ring-ink/25"
          @click="useDemo(account)"
        >
          <span class="font-medium text-ink">{{ account.role }}</span>
          <span class="truncate text-ink-secondary">{{ account.login }}</span>
        </button>
      </div>
    </div>
  </form>
</template>
