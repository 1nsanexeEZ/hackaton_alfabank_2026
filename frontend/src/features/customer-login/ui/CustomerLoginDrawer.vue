<script setup lang="ts">
import { Check, ChevronRight } from 'lucide-vue-next'
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { customer } from '@/entities/customer'
import { clientApi, type DemoAccountDto, type MeDto } from '@/shared/api'
import { ROUTE_PATH } from '@/shared/config'
import { errorMessage } from '@/shared/lib'
import { BaseButton, BaseDrawer, FloatingLetters, TextField } from '@/shared/ui'

import type { AfterLogin, DrawerExit } from '../model/transition'
import LoginSuccessTransition from './LoginSuccessTransition.vue'

/**
 * Вход клиента на сайте: email или телефон и пароль (POST /auth/login). С входом сотрудников
 * в рабочее место не связан — своя сессия, свой токен; учётки сотрудников сюда не пускаем.
 * Если на стенде включён демо-вход, ниже — учётки предпринимателей из сидов: вход одной кнопкой.
 * Форма — в панели справа; открытая часть страницы размыта, по ней плавают буквы «А».
 * После входа на нажатой кнопке — галочка, дальше анимация «сборка в знак» (LoginSuccessTransition):
 * на страницу профиля или, если клиент нажимал «Оформить заявку», в мастер заявки (`next`).
 * Восстановление сессии по сохранённому токену анимацию не запускает — только явный вход здесь.
 */
const props = withDefaults(defineProps<{ description?: string; next?: AfterLogin }>(), {
  description: 'Войдите, чтобы оформить заявку: данные компании загрузим автоматически',
  next: 'profile',
})

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ success: [me: MeDto] }>()

const router = useRouter()

const form = reactive({ login: '', password: '' })
const errors = reactive<{ login?: string; password?: string }>({})
const formError = ref<string | null>(null)
const pending = ref(false)
const demoPending = ref<string | null>(null)
/** Где стоит галочка после входа: `form` — кнопка «Войти», иначе логин демо-учётки */
const succeeded = ref<string | null>(null)
const exit = ref<DrawerExit>('close')

const letters = ref<InstanceType<typeof FloatingLetters> | null>(null)
const transition = ref<InstanceType<typeof LoginSuccessTransition> | null>(null)

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
    succeeded.value = null
    exit.value = 'close'
    if (!demoAccounts.value.length) void loadDemoAccounts()
  },
  { immediate: true },
)

function validate(): boolean {
  errors.login = form.login.trim() ? undefined : 'Введите email или телефон'
  errors.password = form.password ? undefined : 'Введите пароль'
  return !errors.login && !errors.password
}

/** Вход прошёл — анимация сама закроет панель, при необходимости сменит страницу и сообщит об успехе */
function celebrate(me: MeDto, source: string) {
  succeeded.value = source
  const done = () => emit('success', me)
  if (!transition.value) {
    open.value = false
    if (props.next === 'profile') void router.push(ROUTE_PATH.profile)
    done()
    return
  }
  void transition.value.start({
    next: props.next,
    letters: () => letters.value?.snapshot() ?? [],
    close: (how) => {
      exit.value = how
      open.value = false
    },
    navigate: () => router.push(ROUTE_PATH.profile),
    done,
  })
}

async function finish(attempt: () => Promise<MeDto>, source: string) {
  formError.value = null
  let me: MeDto
  try {
    me = await attempt()
  } catch (error) {
    formError.value = errorMessage(error)
    return
  }
  form.password = ''
  celebrate(me, source)
}

async function submit() {
  if (!validate()) return
  pending.value = true
  await finish(() => customer.login(form.login.trim(), form.password), 'form')
  pending.value = false
}

async function loginAsDemo(account: DemoAccountDto) {
  demoPending.value = account.login
  await finish(() => customer.loginWithDemo(account.login), account.login)
  demoPending.value = null
}
</script>

<template>
  <BaseDrawer v-model:open="open" title="Вход в личный кабинет" eyebrow="Личный кабинет" :description="description" :exit="exit">
    <template #backdrop>
      <FloatingLetters ref="letters" />
    </template>

    <form class="space-y-4" novalidate @submit.prevent="submit">
      <div class="space-y-4 transition-opacity duration-200" :class="succeeded && 'opacity-40'">
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
      </div>
      <p v-if="formError" class="rounded-xl bg-brand-soft px-4 py-3 text-sm text-brand" role="alert">
        {{ formError }}
      </p>
      <div class="transition-opacity duration-200" :class="succeeded && succeeded !== 'form' && 'opacity-40'">
        <BaseButton type="submit" size="l" block :loading="pending">
          <template v-if="succeeded === 'form'">
            <Check class="login-check size-6" :stroke-width="3" aria-hidden="true" />
            <span class="sr-only">Вход выполнен</span>
          </template>
          <template v-else>Войти</template>
        </BaseButton>
      </div>
    </form>

    <div v-if="clientDemoAccounts.length" class="rounded-2xl bg-surface-soft p-4">
      <div class="transition-opacity duration-200" :class="succeeded && 'opacity-40'">
        <p class="text-sm font-semibold text-ink">Демо-доступ</p>
        <p class="mt-0.5 text-xs text-ink-secondary">Синтетические предприниматели — вход без пароля</p>
      </div>
      <ul class="mt-3 grid gap-2">
        <li
          v-for="account in clientDemoAccounts"
          :key="account.login"
          class="transition-opacity duration-200"
          :class="succeeded && succeeded !== account.login && 'opacity-40'"
        >
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
            <span v-if="succeeded === account.login" class="flex shrink-0 items-center gap-1 text-xs font-semibold text-success">
              <Check class="login-check size-4" :stroke-width="3" aria-hidden="true" />
              Вход выполнен
            </span>
            <span
              v-else-if="demoPending === account.login"
              class="size-4 shrink-0 animate-spin rounded-full border-2 border-ink-secondary border-r-transparent"
              aria-hidden="true"
            />
            <ChevronRight v-else class="size-4 shrink-0 text-ink-secondary" aria-hidden="true" />
          </button>
        </li>
      </ul>
    </div>
  </BaseDrawer>

  <LoginSuccessTransition ref="transition" />
</template>

<style scoped>
/* Галочка вместо «Войти» — с лёгкой пружиной */
.login-check {
  animation: login-check-pop 240ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
}

@keyframes login-check-pop {
  from {
    opacity: 0;
    transform: scale(0.4);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
</style>
