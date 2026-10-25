<script setup lang="ts">
import {
  ArrowRight,
  BadgeCheck,
  Bell,
  Building2,
  ChevronRight,
  FileText,
  KeyRound,
  LogOut,
  Mail,
  Phone,
  Plus,
  ShieldCheck,
  Sparkles,
  UserRound,
} from 'lucide-vue-next'
import { computed, shallowRef, watch } from 'vue'
import { useRouter } from 'vue-router'

import { CLIENT_STATUS_META, ACTION_REQUIRED_LABEL, isActiveApplication, myApplications } from '@/entities/application'
import { useProductCatalog } from '@/entities/credit-product'
import { customer, useCustomer } from '@/entities/customer'
import { liveFeed } from '@/entities/notification'
import { signOutWithTransition } from '@/features/customer-logout'
import { ClientProfileForm, CompanyConsents, PersonalConsents } from '@/features/edit-client-profile'
import { clientApi, type OrganizationSummaryDto } from '@/shared/api'
import { ROUTE_PATH } from '@/shared/config'
import { formatDate, formatMoney, formatMoneyShort, formatRelativeTime } from '@/shared/lib'
import { AnimatedNumber, BaseBadge, BaseButton, BaseContainer, PanelCard, PatternBackground } from '@/shared/ui'
import { openApplicationCard, openCabinet, openLogin, startApplication } from '@/widgets/apply-flow'

/**
 * Профиль клиента отдельной страницей: кто вошёл, сводка по заявкам и предодобрению, личные данные,
 * согласия, компании с ролью и правами, последние заявки, вход и безопасность.
 * Остальные разделы кабинета (заявка, уведомления, компания) пока открываются модалками поверх страницы.
 * `data-rise` — блоки, которые после входа поднимаются лесенкой (анимация входа в features/customer-login).
 */
const { me, name, logout } = useCustomer()
const { products } = useProductCatalog()

/** В строках черновиков BFF нет названия продукта — берём его из каталога */
const productTitle = (code: string, fallback: string) =>
  fallback || products.value?.find((product) => product.code === code)?.title || 'Заявка на кредит'

const LEGAL_FORM: Record<string, string> = { LLC: 'ООО', IE: 'ИП', JSC: 'АО' }
const MEMBER_ROLE: Record<string, string> = {
  owner: 'Собственник',
  director: 'Руководитель',
  accountant: 'Бухгалтер',
  employee: 'Сотрудник',
}
/** Права внутри компании, которые важны клиенту: может ли он подать и подписать */
const KEY_RIGHTS = [
  { code: 'submit_application', label: 'Подаёт заявки' },
  { code: 'sign', label: 'Подписывает' },
] as const

interface CompanyRow extends OrganizationSummaryDto {
  preApprovedMax: number | null
  preApprovedRate: number | null
  verified: boolean
}

const companies = shallowRef<CompanyRow[] | null>(null)
const companiesError = shallowRef<string | null>(null)

async function loadCompanies() {
  companiesError.value = null
  try {
    const list = (await clientApi.listOrganizations()).filter((item) => item.my_role !== null)
    // Предодобрение и проверка — из главного экрана BFF по каждой компании; не ответил — показываем без них
    companies.value = await Promise.all(
      list.map(async (item) => {
        const dashboard = await clientApi.dashboard(item.id).catch(() => null)
        const counters = dashboard?.counters
        return {
          ...item,
          preApprovedMax: counters?.pre_approved_max_amount ? Number(counters.pre_approved_max_amount) : null,
          preApprovedRate: counters?.pre_approved_rate_from ? Number(counters.pre_approved_rate_from) : null,
          verified: dashboard?.organization?.verification_status === 'verified',
        }
      }),
    )
  } catch {
    companiesError.value = 'Не удалось загрузить компании'
  }
}

watch(
  () => me.value?.id ?? null,
  (id) => {
    companies.value = null
    if (!id) return
    void loadCompanies()
    if (!myApplications.state.items && !myApplications.state.loading) void myApplications.load()
  },
  { immediate: true },
)

const initials = computed(() => {
  const profile = me.value?.profile
  const letters = [profile?.first_name, profile?.last_name].filter(Boolean).map((part) => part!.charAt(0))
  return (letters.join('') || name.value.charAt(0) || 'К').toUpperCase()
})
const fullName = computed(() => {
  const profile = me.value?.profile
  const parts = [profile?.last_name, profile?.first_name, profile?.middle_name].filter(Boolean)
  return parts.length ? parts.join(' ') : name.value
})

const applications = computed(() => myApplications.state.items ?? [])
const active = computed(() => applications.value.filter(isActiveApplication))
const waiting = computed(() => applications.value.filter((item) => item.action_required !== 'none'))
const recent = computed(() => applications.value.slice(0, 4))
const bestOffer = computed(() => {
  const offers = (companies.value ?? []).filter((item) => item.preApprovedMax)
  return offers.length ? Math.max(...offers.map((item) => item.preApprovedMax!)) : null
})

const count = (value: number) => String(value)

/** Счётчики шапки: value — число (null — ещё грузится), empty — показать «—» вместо нуля */
const stats = computed(() => [
  { label: 'Заявок в работе', value: myApplications.state.items ? active.value.length : null, format: count, icon: FileText },
  {
    label: 'Ждут вашего действия',
    value: myApplications.state.items ? waiting.value.length : null,
    format: count,
    icon: Sparkles,
    accent: waiting.value.length > 0,
  },
  {
    label: 'Предодобрено до',
    value: companies.value ? (bestOffer.value ?? 0) : null,
    empty: companies.value !== null && !bestOffer.value,
    format: formatMoneyShort,
    icon: BadgeCheck,
  },
  { label: 'Новых уведомлений', value: liveFeed.state.unread, format: count, icon: Bell },
])

const router = useRouter()

/** Выход «чёрной дырой»: сессия стирается сразу, открывается главная */
function signOut() {
  signOutWithTransition({
    logout: () => {
      logout()
      myApplications.clear()
    },
    navigate: () => router.push(ROUTE_PATH.home),
  })
}
</script>

<template>
  <!-- Не вошёл: страница не пустая, а с понятным шагом -->
  <section v-if="!customer.state.token" class="py-24">
    <BaseContainer class="flex flex-col items-center text-center">
      <span class="flex size-16 items-center justify-center rounded-full bg-surface text-ink-secondary">
        <UserRound class="size-8" aria-hidden="true" />
      </span>
      <h1 class="text-title mt-6">Профиль доступен после входа</h1>
      <p class="mt-3 max-w-md text-ink-secondary">
        Войдите, чтобы увидеть свои данные, компании, согласия и заявки.
      </p>
      <BaseButton class="mt-8" size="l" @click="openLogin">Войти</BaseButton>
    </BaseContainer>
  </section>

  <template v-else-if="me">
    <!-- Шапка профиля в стиле первого экрана -->
    <section class="relative overflow-hidden bg-night text-on-night">
      <PatternBackground />
      <div
        class="pointer-events-none absolute -top-40 right-0 size-[30rem] rounded-full bg-brand/20 blur-[120px]"
        aria-hidden="true"
      />
      <BaseContainer class="relative py-10 lg:py-14">
        <div class="flex flex-col gap-8 lg:flex-row lg:items-end lg:justify-between">
          <div class="flex items-center gap-5" data-rise>
            <span
              class="flex size-20 shrink-0 items-center justify-center rounded-3xl bg-brand text-2xl font-bold text-white shadow-[0_1rem_2.5rem_rgb(239_49_36/0.35)] lg:size-24 lg:text-3xl"
              aria-hidden="true"
            >
              {{ initials }}
            </span>
            <div class="min-w-0">
              <p class="text-sm text-on-night-secondary">Личный кабинет</p>
              <h1 class="mt-1 text-2xl font-bold outline-none lg:text-4xl" tabindex="-1">{{ fullName }}</h1>
              <p class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-on-night-secondary">
                <span v-if="me.profile?.position">{{ me.profile.position }}</span>
                <span v-if="me.email" class="flex items-center gap-1.5"><Mail class="size-4" aria-hidden="true" />{{ me.email }}</span>
                <span v-if="me.phone" class="flex items-center gap-1.5"><Phone class="size-4" aria-hidden="true" />{{ me.phone }}</span>
              </p>
            </div>
          </div>
          <div class="flex flex-col gap-3 sm:flex-row" data-rise>
            <BaseButton size="l" @click="startApplication()">
              <Plus class="size-4" aria-hidden="true" />
              Оформить заявку
            </BaseButton>
            <BaseButton size="l" variant="glass" @click="openCabinet('applications')">Мои заявки</BaseButton>
          </div>
        </div>

        <ul class="mt-10 grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
          <li
            v-for="stat in stats"
            :key="stat.label"
            class="flex min-h-28 flex-col justify-between gap-3 rounded-3xl bg-night-glass p-4 lg:p-5"
            data-rise
          >
            <span
              class="flex size-9 items-center justify-center rounded-full"
              :class="stat.accent ? 'bg-brand text-white' : 'bg-white/10'"
            >
              <component :is="stat.icon" class="size-4" aria-hidden="true" />
            </span>
            <div>
              <p v-if="stat.value !== null" class="text-xl font-bold lg:text-2xl">
                <template v-if="stat.empty">—</template>
                <AnimatedNumber v-else :value="stat.value" :format="stat.format" animate-on-mount />
              </p>
              <p v-else class="h-7 w-16 animate-pulse rounded-lg bg-white/10" aria-label="Загружаем" />
              <p class="mt-0.5 text-sm text-on-night-secondary">{{ stat.label }}</p>
            </div>
          </li>
        </ul>
      </BaseContainer>
    </section>

    <section class="bg-surface-soft py-10 lg:py-14">
      <BaseContainer>
        <div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px] lg:items-start">
          <div class="space-y-6">
            <PanelCard data-rise title="Личные данные" description="Как к вам обращаться в кабинете и в документах">
              <ClientProfileForm :key="me.id" />
            </PanelCard>

            <PanelCard data-rise title="Согласия" description="Действуют для всех заявок — повторно давать их не нужно">
              <PersonalConsents />
              <CompanyConsents class="mt-6" />
            </PanelCard>
          </div>

          <aside class="space-y-6">
            <PanelCard data-rise title="Мои компании" flush>
              <template #actions>
                <button
                  type="button"
                  class="text-sm font-medium text-ink-secondary hover:text-ink"
                  @click="openCabinet('company')"
                >
                  Подробнее
                </button>
              </template>
              <p v-if="companiesError" class="px-5 pb-5 text-sm text-brand">{{ companiesError }}</p>
              <ul v-else-if="companies" class="divide-y divide-line">
                <li v-for="company in companies" :key="company.id">
                  <button
                    type="button"
                    class="group flex w-full items-start gap-3 px-5 py-4 text-left transition-colors hover:bg-surface-soft"
                    @click="openCabinet('company')"
                  >
                    <span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-surface text-ink-secondary">
                      <Building2 class="size-5" aria-hidden="true" />
                    </span>
                    <span class="min-w-0 flex-1">
                      <span class="flex items-center gap-1.5 font-semibold text-ink">
                        <span class="truncate">{{ company.name }}</span>
                        <BadgeCheck v-if="company.verified" class="size-4 shrink-0 text-success" aria-label="Проверена" />
                      </span>
                      <span class="mt-0.5 block text-xs text-ink-secondary">
                        {{ LEGAL_FORM[company.legal_form] ?? company.legal_form }} · ИНН {{ company.inn }} ·
                        {{ MEMBER_ROLE[company.my_role ?? ''] ?? company.my_role }}
                      </span>
                      <span class="mt-2 flex flex-wrap gap-1.5">
                        <BaseBadge
                          v-for="right in KEY_RIGHTS"
                          :key="right.code"
                          :tone="company.my_permissions.includes(right.code) ? 'success' : 'neutral'"
                        >
                          {{ company.my_permissions.includes(right.code) ? right.label : `Не ${right.label.toLowerCase()}` }}
                        </BaseBadge>
                      </span>
                      <span v-if="company.preApprovedMax" class="mt-2 block text-xs font-medium text-success">
                        Предодобрено до {{ formatMoney(company.preApprovedMax) }}<template v-if="company.preApprovedRate">
                          · от {{ company.preApprovedRate }}%</template
                        >
                      </span>
                    </span>
                    <ChevronRight class="mt-2.5 size-4 shrink-0 text-ink-muted transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
                  </button>
                </li>
                <li v-if="!companies.length" class="px-5 py-4 text-sm text-ink-secondary">Вы пока не участник ни одной компании</li>
              </ul>
              <div v-else class="space-y-3 px-5 pb-5">
                <p v-for="index in 2" :key="index" class="h-16 animate-pulse rounded-xl bg-surface" />
              </div>
            </PanelCard>

            <PanelCard data-rise title="Последние заявки" flush>
              <template #actions>
                <button
                  type="button"
                  class="text-sm font-medium text-ink-secondary hover:text-ink"
                  @click="openCabinet('applications')"
                >
                  Все
                </button>
              </template>
              <ul v-if="recent.length" class="divide-y divide-line">
                <li v-for="item in recent" :key="item.id">
                  <button
                    type="button"
                    class="group flex w-full items-center gap-3 px-5 py-3.5 text-left transition-colors hover:bg-surface-soft"
                    @click="openApplicationCard(item.id)"
                  >
                    <span class="min-w-0 flex-1">
                      <span class="block truncate text-sm font-semibold text-ink">
                        {{ productTitle(item.product_code, item.product_name) }}
                      </span>
                      <span class="mt-0.5 block text-xs text-ink-secondary">
                        № {{ item.number }} · {{ formatRelativeTime(item.updated_at) }}
                      </span>
                      <span v-if="item.action_required !== 'none'" class="mt-1 block text-xs font-medium text-brand">
                        {{ ACTION_REQUIRED_LABEL[item.action_required] ?? 'Нужно ваше действие' }}
                      </span>
                    </span>
                    <BaseBadge :tone="CLIENT_STATUS_META[item.client_status].tone">
                      {{ CLIENT_STATUS_META[item.client_status].label }}
                    </BaseBadge>
                  </button>
                </li>
              </ul>
              <div v-else-if="myApplications.state.items" class="px-5 pb-5">
                <p class="text-sm text-ink-secondary">Заявок пока нет — подберём кредит под задачу за пару минут.</p>
                <button
                  type="button"
                  class="mt-3 flex items-center gap-1.5 text-sm font-semibold text-brand"
                  @click="startApplication()"
                >
                  Оформить первую заявку
                  <ArrowRight class="size-4" aria-hidden="true" />
                </button>
              </div>
              <div v-else class="space-y-3 px-5 pb-5">
                <p v-for="index in 3" :key="index" class="h-12 animate-pulse rounded-xl bg-surface" />
              </div>
            </PanelCard>

            <PanelCard data-rise title="Вход и безопасность">
              <dl class="space-y-3 text-sm">
                <div class="flex items-start gap-3">
                  <KeyRound class="mt-0.5 size-4 shrink-0 text-ink-secondary" aria-hidden="true" />
                  <div>
                    <dt class="text-ink-secondary">Логин</dt>
                    <dd class="font-medium text-ink">{{ [me.email, me.phone].filter(Boolean).join(' или ') }}</dd>
                  </div>
                </div>
                <div class="flex items-start gap-3">
                  <ShieldCheck class="mt-0.5 size-4 shrink-0 text-ink-secondary" aria-hidden="true" />
                  <div>
                    <dt class="text-ink-secondary">Подпись документов</dt>
                    <dd class="font-medium text-ink">Повторный ввод пароля</dd>
                  </div>
                </div>
                <div class="flex items-start gap-3">
                  <UserRound class="mt-0.5 size-4 shrink-0 text-ink-secondary" aria-hidden="true" />
                  <div>
                    <dt class="text-ink-secondary">В кабинете с</dt>
                    <dd class="font-medium text-ink">{{ formatDate(me.created_at) }}</dd>
                  </div>
                </div>
              </dl>
              <p class="mt-4 rounded-xl bg-surface-soft p-3 text-xs text-ink-secondary">
                Email, телефон и пароль меняет банк — обратитесь к своему менеджеру.
              </p>
              <BaseButton class="mt-4" variant="secondary" block @click="signOut">
                <LogOut class="size-4" aria-hidden="true" />
                Выйти из кабинета
              </BaseButton>
            </PanelCard>
          </aside>
        </div>
      </BaseContainer>
    </section>
  </template>

  <!-- Токен есть, профиль ещё грузится -->
  <section v-else class="py-24">
    <BaseContainer>
      <p class="mx-auto h-24 max-w-3xl animate-pulse rounded-3xl bg-surface" aria-label="Загружаем профиль" />
    </BaseContainer>
  </section>
</template>
