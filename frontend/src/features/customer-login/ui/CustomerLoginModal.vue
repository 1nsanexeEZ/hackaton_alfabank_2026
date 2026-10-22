<script setup lang="ts">
import { ChevronRight } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'

import { customer } from '@/entities/customer'
import { clientApi, type DemoAccountDto, type MeDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'
import { BaseButton, BaseModal, TextField } from '@/shared/ui'

/**
 * Вход клиента на сайте: email или телефон и пароль (POST /auth/login). С входом сотрудников
 * в рабочее место не связан — своя сессия, свой токен; учётки сотрудников сюда не пускаем.
 * Если на стенде включён демо-вход, ниже — учётки предпринимателей из сидов: вход одной кнопкой.
 */
withDefaults(defineProps<{ description?: string }>(), {
  description: 'Войдите, чтобы оформить заявку: данные компании подтянем автоматически',
})

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ success: [me: MeDto] }>()

const form = reactive({ login: '', password: '' })
const errors = reactive<{ login?: string; password?: string }>({})
const formError = ref<string | null>(null)
const pending = ref(false)
const demoPending = ref<string | null>(null)

const demoAccounts = ref<DemoAccountDto[]>([])
const clientDemoAccounts = computed(() => demoAccounts.value.filter((account) => account.role === 'client'))

async function loadDemoAccounts() {
  try {
    demoAccounts.value = await clientApi.demoAccounts()
  } catch {
    // Демо-вход выключен (404) — просто не показываем список
    demoAccounts.value = []
  }
}

watch(
  open,
  (isOpen) => {
    if (!isOpen) return
    formError.value = null
    if (!demoAccounts.value.length) void loadDemoAccounts()
  },
  { immediate: true },
)

function validate(): boolean {
  errors.login = form.login.trim() ? undefined : 'Введите email или телефон'
  errors.password = form.password ? undefined : 'Введите пароль'
  return !errors.login && !errors.password
}

async function finish(attempt: () => Promise<MeDto>) {
  formError.value = null
  try {
    const me = await attempt()
    form.password = ''
    open.value = false
    emit('success', me)
  } catch (error) {
    formError.value = errorMessage(error)
  }
}

async function submit() {
  if (!validate()) return
  pending.value = true
  await finish(() => customer.login(form.login.trim(), form.password))
  pending.value = false
}

async function loginAsDemo(account: DemoAccountDto) {
  demoPending.value = account.login
  await finish(() => customer.loginWithDemo(account.login))
  demoPending.value = null
}
</script>

<template>
  <BaseModal v-model:open="open" title="Вход в личный кабинет" :description="description">
    <form class="space-y-4" novalidate @submit.prevent="submit">
      <TextField
        v-model="form.login"
        label="Email или телефон"
        type="email"
        autocomplete="username"
        placeholder="name@company.ru"
        :error="errors.login"
      />
      <TextField
        v-model="form.password"
        label="Пароль"
        type="password"
        autocomplete="current-password"
        :error="errors.password"
      />
      <p v-if="formError" class="rounded-xl bg-brand-soft px-4 py-3 text-sm text-brand" role="alert">
        {{ formError }}
      </p>
      <BaseButton type="submit" size="l" block :loading="pending">Войти</BaseButton>
    </form>

    <div v-if="clientDemoAccounts.length" class="mt-6 rounded-2xl bg-surface-soft p-4">
      <p class="text-sm font-semibold text-ink">Демо-доступ</p>
      <p class="mt-0.5 text-xs text-ink-secondary">Синтетические предприниматели — вход без пароля</p>
      <ul class="mt-3 grid gap-2">
        <li v-for="account in clientDemoAccounts" :key="account.login">
          <button
            type="button"
            class="flex w-full items-center justify-between gap-3 rounded-xl bg-white px-3 py-2.5 text-left ring-1 ring-line transition hover:ring-ink/25 disabled:opacity-60"
            :disabled="demoPending !== null"
            @click="loginAsDemo(account)"
          >
            <span class="min-w-0">
              <span class="block truncate text-sm font-medium text-ink">{{ account.full_name }}</span>
              <span class="block truncate text-xs text-ink-secondary">{{ account.caption }}</span>
            </span>
            <span
              v-if="demoPending === account.login"
              class="size-4 shrink-0 animate-spin rounded-full border-2 border-ink-secondary border-r-transparent"
              aria-hidden="true"
            />
            <ChevronRight v-else class="size-4 shrink-0 text-ink-secondary" aria-hidden="true" />
          </button>
        </li>
      </ul>
    </div>
  </BaseModal>
</template>
