<script setup lang="ts">
import { Bell, Building2, ChevronDown, FileText, LogIn, LogOut, Menu, UserRound, X, type LucideIcon } from 'lucide-vue-next'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { customer, useCustomer } from '@/entities/customer'
import { liveFeed } from '@/entities/notification'
import { LANDING_NAV, ROUTE_PATH, sectionHref } from '@/shared/config'
import { AppLogo, BaseButton, BaseContainer } from '@/shared/ui'

/**
 * Кнопки «Оформить заявку» и «Войти» не решают сами, куда вести: страница или приложение
 * передают это в поток заявки, где проверяется вход.
 */
const emit = defineEmits<{ apply: []; login: []; open: [section: CabinetSection] }>()

/** Разделы кабинета клиента — открываются модалками поверх сайта (widgets/apply-flow) */
type CabinetSection = 'applications' | 'notifications' | 'company' | 'profile'

const CABINET_LINKS: readonly { section: CabinetSection; label: string; icon: LucideIcon }[] = [
  { section: 'applications', label: 'Мои заявки', icon: FileText },
  { section: 'notifications', label: 'Уведомления', icon: Bell },
  { section: 'company', label: 'Компания', icon: Building2 },
  { section: 'profile', label: 'Профиль', icon: UserRound },
]

const unread = computed(() => liveFeed.state.unread)

function openSection(section: CabinetSection) {
  closeAccount()
  closeMenu()
  emit('open', section)
}

const { me, isAuthenticated, name, logout } = useCustomer()

const isMenuOpen = ref(false)
const route = useRoute()

// Подтягиваем профиль по сохранённому токену, чтобы сразу показать, кто вошёл
onMounted(() => void customer.restore())

function closeMenu() {
  isMenuOpen.value = false
}

/*
 * Меню аккаунта: имя и «Выйти» в одной кнопке, чтобы шапка помещалась на 1024 px.
 * Имя на самой кнопке — с 1280 px, в раскрытом меню — всегда.
 */
const isAccountOpen = ref(false)
const account = ref<HTMLElement>()
const contact = computed(() => me.value?.email ?? me.value?.phone ?? '')

function closeAccount(returnFocus = false) {
  if (!isAccountOpen.value) return
  isAccountOpen.value = false
  if (returnFocus) account.value?.querySelector<HTMLElement>('[aria-haspopup]')?.focus()
}

function toggleAccount() {
  isAccountOpen.value = !isAccountOpen.value
  if (isAccountOpen.value) void nextTick(() => account.value?.querySelector<HTMLElement>('[role=menuitem]')?.focus())
}

function signOut() {
  closeAccount()
  closeMenu()
  logout()
}

function onPointerDownOutside(event: PointerEvent) {
  if (!account.value?.contains(event.target as Node)) closeAccount()
}

watch(isAccountOpen, (isOpen) => {
  if (isOpen) document.addEventListener('pointerdown', onPointerDownOutside)
  else document.removeEventListener('pointerdown', onPointerDownOutside)
})

function apply() {
  closeMenu()
  emit('apply')
}

function login() {
  closeMenu()
  emit('login')
}

function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  closeMenu()
  closeAccount(true)
}

// На десктопе мобильное меню не нужно: закрываем его, если окно расширили
const desktopQuery = typeof window !== 'undefined' ? window.matchMedia('(min-width: 64rem)') : null

function onDesktopChange(event: MediaQueryListEvent) {
  if (event.matches) closeMenu()
}

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  desktopQuery?.addEventListener('change', onDesktopChange)
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('pointerdown', onPointerDownOutside)
  desktopQuery?.removeEventListener('change', onDesktopChange)
})

watch(
  () => route.fullPath,
  () => {
    closeMenu()
    closeAccount()
  },
)
</script>

<template>
  <header class="sticky top-0 z-50 bg-night text-on-night">
    <BaseContainer class="flex h-16 items-center justify-between gap-6 lg:h-18">
      <RouterLink :to="ROUTE_PATH.home" class="shrink-0 rounded-lg" aria-label="Кредитный кабинет — на главную">
        <AppLogo inverted />
      </RouterLink>

      <nav class="hidden lg:block" aria-label="Разделы">
        <ul class="flex items-center gap-6 xl:gap-8">
          <li v-for="link in LANDING_NAV" :key="link.section">
            <a
              :href="sectionHref(link.section)"
              class="text-[15px] font-medium whitespace-nowrap text-on-night-secondary transition-colors hover:text-on-night"
            >
              {{ link.label }}
            </a>
          </li>
        </ul>
      </nav>

      <div class="flex items-center gap-2">
        <!-- max-*:hidden, а не hidden sm:inline-flex: у BaseButton свой display, обычный hidden его не перебьёт -->
        <div v-if="isAuthenticated" ref="account" class="relative max-sm:hidden">
          <BaseButton
            variant="glass"
            size="s"
            aria-haspopup="menu"
            aria-controls="account-menu"
            :aria-expanded="isAccountOpen"
            :aria-label="unread ? `Аккаунт: ${name}, новых уведомлений: ${unread}` : `Аккаунт: ${name}`"
            @click="toggleAccount"
          >
            <UserRound class="size-4 shrink-0" aria-hidden="true" />
            <span class="max-w-40 truncate max-xl:hidden">{{ name }}</span>
            <span
              v-if="unread"
              class="flex h-4.5 min-w-4.5 items-center justify-center rounded-full bg-brand px-1 text-[10px] leading-none font-bold text-white"
              :aria-label="`Новых уведомлений: ${unread}`"
            >
              {{ unread > 99 ? '99+' : unread }}
            </span>
            <ChevronDown
              class="size-4 shrink-0 transition-transform duration-200"
              :class="isAccountOpen && 'rotate-180'"
              aria-hidden="true"
            />
          </BaseButton>
          <Transition
            enter-from-class="opacity-0 -translate-y-1"
            enter-active-class="transition duration-150"
            leave-to-class="opacity-0 -translate-y-1"
            leave-active-class="transition duration-100"
          >
            <div
              v-if="isAccountOpen"
              id="account-menu"
              role="menu"
              aria-label="Аккаунт"
              class="absolute top-full right-0 mt-2 w-64 rounded-2xl bg-white p-1.5 text-ink shadow-[0_1.25rem_3rem_rgb(18_18_19/0.18),0_0_0_1px_var(--color-line)]"
            >
              <div class="px-3.5 py-2.5">
                <p class="truncate text-sm font-semibold">{{ name }}</p>
                <p v-if="contact" class="truncate text-xs text-ink-secondary">{{ contact }}</p>
              </div>
              <button
                v-for="link in CABINET_LINKS"
                :key="link.section"
                type="button"
                role="menuitem"
                class="flex min-h-11 w-full items-center gap-2.5 rounded-xl px-3.5 text-left text-sm font-medium transition-colors outline-none hover:bg-surface focus-visible:bg-surface"
                @click="openSection(link.section)"
              >
                <component :is="link.icon" class="size-4 text-ink-secondary" aria-hidden="true" />
                <span class="flex-1">{{ link.label }}</span>
                <span
                  v-if="link.section === 'notifications' && unread"
                  class="rounded-full bg-brand px-1.5 py-0.5 text-[11px] leading-none font-bold text-white"
                >
                  {{ unread }}
                </span>
              </button>
              <div class="my-1 h-px bg-line" aria-hidden="true" />
              <button
                type="button"
                role="menuitem"
                class="flex min-h-11 w-full items-center gap-2.5 rounded-xl px-3.5 text-left text-sm font-medium transition-colors outline-none hover:bg-surface focus-visible:bg-surface"
                @click="signOut"
              >
                <LogOut class="size-4 text-ink-secondary" aria-hidden="true" />
                Выйти
              </button>
            </div>
          </Transition>
        </div>
        <BaseButton v-else variant="glass" size="s" class="max-sm:hidden" @click="login">
          <LogIn class="size-4" aria-hidden="true" />
          Войти
        </BaseButton>
        <BaseButton size="s" class="max-md:hidden" @click="apply">Оформить заявку</BaseButton>
        <button
          type="button"
          class="relative -mr-2 flex size-10 items-center justify-center rounded-lg text-on-night transition-colors hover:bg-night-glass lg:hidden"
          :aria-expanded="isMenuOpen"
          aria-controls="mobile-menu"
          :aria-label="isMenuOpen ? 'Закрыть меню' : 'Открыть меню'"
          @click="isMenuOpen = !isMenuOpen"
        >
          <X v-if="isMenuOpen" class="size-6" aria-hidden="true" />
          <Menu v-else class="size-6" aria-hidden="true" />
          <span v-if="isAuthenticated && unread && !isMenuOpen" class="absolute top-2 right-1.5 size-2.5 rounded-full bg-brand ring-2 ring-night" aria-hidden="true" />
        </button>
      </div>
    </BaseContainer>

    <Transition
      enter-from-class="opacity-0 -translate-y-2"
      enter-active-class="transition duration-200"
      leave-to-class="opacity-0 -translate-y-2"
      leave-active-class="transition duration-150"
    >
      <div v-if="isMenuOpen" id="mobile-menu" class="border-t border-night-line lg:hidden">
        <BaseContainer class="pt-2 pb-6">
          <nav aria-label="Разделы">
            <ul>
              <li v-for="link in LANDING_NAV" :key="link.section">
                <a
                  :href="sectionHref(link.section)"
                  class="block border-b border-night-line py-4 text-lg font-medium text-on-night"
                  @click="closeMenu"
                >
                  {{ link.label }}
                </a>
              </li>
            </ul>
          </nav>
          <ul v-if="isAuthenticated" class="mt-4 grid grid-cols-2 gap-2" aria-label="Кабинет">
            <li v-for="link in CABINET_LINKS" :key="link.section">
              <button
                type="button"
                class="flex w-full items-center gap-2.5 rounded-xl bg-night-glass px-3.5 py-3 text-left text-sm font-medium text-on-night"
                @click="openSection(link.section)"
              >
                <component :is="link.icon" class="size-4 shrink-0" aria-hidden="true" />
                <span class="flex-1">{{ link.label }}</span>
                <span v-if="link.section === 'notifications' && unread" class="rounded-full bg-brand px-1.5 py-0.5 text-[11px] leading-none font-bold text-white">
                  {{ unread }}
                </span>
              </button>
            </li>
          </ul>
          <div class="mt-6 grid gap-3 sm:grid-cols-2">
            <BaseButton v-if="isAuthenticated" variant="glass" block @click="signOut">
              <LogOut class="size-4" aria-hidden="true" />
              Выйти · {{ name }}
            </BaseButton>
            <BaseButton v-else variant="glass" block @click="login">
              <LogIn class="size-4" aria-hidden="true" />
              Войти в кабинет
            </BaseButton>
            <BaseButton block @click="apply">Оформить заявку</BaseButton>
          </div>
        </BaseContainer>
      </div>
    </Transition>
  </header>
</template>
