<script setup lang="ts">
import { LogOut, Menu, UserRound, X } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

import { roleTitle } from '@/entities/role'
import { useSession } from '@/entities/session'
import { API_MODE } from '@/shared/api'
import { ADMIN_ROUTE } from '@/shared/config'
import { AppLogo } from '@/shared/ui'

import { ADMIN_NAVIGATION } from '../model/navigation'

/** Каркас рабочего места: тёмное меню слева, светлая рабочая область справа */
const { me, name, can, logout } = useSession()
const route = useRoute()
const router = useRouter()

const isMenuOpen = ref(false)

const navigation = computed(() =>
  ADMIN_NAVIGATION.map((group) => ({ ...group, items: group.items.filter((item) => can(item.permission)) })).filter(
    (group) => group.items.length,
  ),
)

const initials = computed(() =>
  name.value
    .split(' ')
    .map((part) => part.charAt(0))
    .join('')
    .slice(0, 2)
    .toUpperCase(),
)

function isCurrent(routeName: string) {
  // Карточка заявки подсвечивает пункт «Заявки»
  if (routeName === ADMIN_ROUTE.applications && route.name === ADMIN_ROUTE.application) return true
  return route.name === routeName
}

async function signOut() {
  logout()
  await router.push({ name: ADMIN_ROUTE.login })
}

watch(() => route.fullPath, () => (isMenuOpen.value = false))
</script>

<template>
  <div class="min-h-dvh bg-surface-soft lg:pl-64">
    <!-- Мобильная шапка -->
    <header class="sticky top-0 z-40 flex h-14 items-center justify-between bg-night px-4 text-on-night lg:hidden">
      <RouterLink :to="{ name: ADMIN_ROUTE.dashboard }" aria-label="На обзор">
        <AppLogo inverted />
      </RouterLink>
      <button
        type="button"
        class="-mr-2 flex size-10 items-center justify-center rounded-lg hover:bg-night-glass"
        :aria-expanded="isMenuOpen"
        aria-controls="admin-sidebar"
        :aria-label="isMenuOpen ? 'Закрыть меню' : 'Открыть меню'"
        @click="isMenuOpen = !isMenuOpen"
      >
        <X v-if="isMenuOpen" class="size-6" aria-hidden="true" />
        <Menu v-else class="size-6" aria-hidden="true" />
      </button>
    </header>

    <div v-if="isMenuOpen" class="fixed inset-0 z-40 bg-night/50 lg:hidden" aria-hidden="true" @click="isMenuOpen = false" />

    <aside
      id="admin-sidebar"
      :class="[
        'fixed inset-y-0 left-0 z-50 flex w-64 flex-col bg-night text-on-night transition-transform',
        isMenuOpen ? 'translate-x-0' : 'max-lg:-translate-x-full',
      ]"
    >
      <div class="flex h-18 shrink-0 items-center px-5">
        <RouterLink :to="{ name: ADMIN_ROUTE.dashboard }" class="rounded-lg" aria-label="На обзор">
          <AppLogo inverted />
        </RouterLink>
      </div>

      <nav class="flex-1 overflow-y-auto px-3 pb-4" aria-label="Разделы админки">
        <div v-for="group in navigation" :key="group.title" class="mt-4 first:mt-1">
          <p class="px-3 pb-2 text-[11px] font-semibold tracking-wider text-on-night-secondary uppercase">
            {{ group.title }}
          </p>
          <ul class="space-y-0.5">
            <li v-for="item in group.items" :key="item.route">
              <RouterLink
                :to="{ name: item.route }"
                :aria-current="isCurrent(item.route) ? 'page' : undefined"
                :class="[
                  'flex h-10 items-center gap-3 rounded-lg px-3 text-sm font-medium transition-colors',
                  isCurrent(item.route)
                    ? 'bg-white text-ink'
                    : 'text-on-night-secondary hover:bg-night-glass hover:text-on-night',
                ]"
              >
                <component :is="item.icon" class="size-[18px] shrink-0" aria-hidden="true" />
                {{ item.label }}
              </RouterLink>
            </li>
          </ul>
        </div>
      </nav>

      <div class="shrink-0 border-t border-night-line p-3">
        <p
          v-if="API_MODE === 'mock'"
          class="mb-3 rounded-lg bg-night-glass px-3 py-2 text-xs leading-snug text-on-night-secondary"
        >
          Демо-режим: данные синтетические и хранятся в браузере
        </p>
        <div class="flex items-center gap-2">
          <RouterLink
            :to="{ name: ADMIN_ROUTE.profile }"
            class="flex min-w-0 flex-1 items-center gap-3 rounded-lg p-2 transition-colors hover:bg-night-glass"
            :aria-current="route.name === ADMIN_ROUTE.profile ? 'page' : undefined"
          >
            <span class="flex size-9 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-bold text-white">
              <template v-if="initials">{{ initials }}</template>
              <UserRound v-else class="size-4" aria-hidden="true" />
            </span>
            <span class="min-w-0 leading-tight">
              <span class="block truncate text-sm font-semibold">{{ name }}</span>
              <span class="block truncate text-xs text-on-night-secondary">{{ me ? roleTitle(me.role.name) : '' }}</span>
            </span>
          </RouterLink>
          <button
            type="button"
            class="flex size-9 shrink-0 items-center justify-center rounded-lg text-on-night-secondary transition-colors hover:bg-night-glass hover:text-on-night"
            aria-label="Выйти"
            title="Выйти"
            @click="signOut"
          >
            <LogOut class="size-[18px]" aria-hidden="true" />
          </button>
        </div>
      </div>
    </aside>

    <main class="px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
      <RouterView />
    </main>
  </div>
</template>
