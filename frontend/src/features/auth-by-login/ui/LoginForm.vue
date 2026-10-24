<script setup lang="ts">
import { computed, reactive, ref } from 'vue'

import { roleTitle } from '@/entities/role'
import { canEnterAdmin, session } from '@/entities/session'
import { identityApi, type DemoAccountDto, type MeDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'
import { BaseButton, TextField } from '@/shared/ui'

/**
 * Вход сотрудника по email или телефону и паролю (POST /auth/login). На стенде с демо-входом
 * (DEMO_LOGIN_ENABLED) ниже — учётки сотрудников из GET /auth/demo-accounts: вход одной кнопкой
 */
const emit = defineEmits<{ success: [me: MeDto] }>()

const form = reactive({ login: '', password: '' })
const errors = reactive<{ login?: string; password?: string }>({})
const formError = ref<string | null>(null)
const pending = ref(false)

const demoAccounts = ref<DemoAccountDto[]>([])
const staffDemoAccounts = computed(() => demoAccounts.value.filter((account) => account.role !== 'client'))
const demoPending = ref<string | null>(null)

// 404 — демо-вход на стенде выключен, блока просто нет
identityApi
  .demoAccounts()
  .then((accounts) => (demoAccounts.value = accounts))
  .catch(() => undefined)

function validate(): boolean {
  errors.login = form.login.trim() ? undefined : 'Введите email или телефон'
  errors.password = form.password ? undefined : 'Введите пароль'
  return !errors.login && !errors.password
}

/** Пускаем только сотрудников: клиент со своими правами в админку не входит */
function finish(me: MeDto) {
  if (!canEnterAdmin(me)) {
    session.logout()
    formError.value = 'У этой учётной записи нет доступа к рабочему месту сотрудника'
    return
  }
  emit('success', me)
}

async function submit() {
  formError.value = null
  if (!validate()) return
  pending.value = true
  try {
    finish(await session.login(form.login.trim(), form.password))
  } catch (error) {
    formError.value = errorMessage(error)
  } finally {
    pending.value = false
  }
}

async function enterDemo(account: DemoAccountDto) {
  formError.value = null
  demoPending.value = account.login
  try {
    finish(await session.demoLogin(account.login))
  } catch (error) {
    formError.value = errorMessage(error)
  } finally {
    demoPending.value = null
  }
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

    <div v-if="staffDemoAccounts.length" class="rounded-2xl bg-surface-soft p-4">
      <p class="text-sm font-semibold text-ink">Демо-доступ</p>
      <p class="mt-0.5 text-xs text-ink-secondary">Вход без пароля — только на демо-стенде</p>
      <div class="mt-3 grid gap-2">
        <button
          v-for="account in staffDemoAccounts"
          :key="account.login"
          type="button"
          class="flex items-center justify-between gap-3 rounded-xl bg-white px-3 py-2.5 text-left text-sm ring-1 ring-line transition hover:ring-ink/25 disabled:opacity-60"
          :disabled="Boolean(demoPending)"
          @click="enterDemo(account)"
        >
          <span class="min-w-0">
            <span class="block font-medium text-ink">{{ account.caption || roleTitle(account.role) }}</span>
            <span class="block truncate text-xs text-ink-secondary">{{ account.full_name }}</span>
          </span>
          <span class="min-w-0 truncate text-xs text-ink-secondary">{{ demoPending === account.login ? 'Входим…' : account.login }}</span>
        </button>
      </div>
    </div>
  </form>
</template>
