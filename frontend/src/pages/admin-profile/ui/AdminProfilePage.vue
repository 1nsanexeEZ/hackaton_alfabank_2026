<script setup lang="ts">
import { computed } from 'vue'

import { PERMISSION_GROUPS, POLICY_META, roleTitle } from '@/entities/role'
import { session, useSession } from '@/entities/session'
import { ProfileForm } from '@/features/edit-profile'
import { API_MODE } from '@/shared/api'
import { formatDateTime } from '@/shared/lib'
import { BaseBadge, PanelCard } from '@/shared/ui'
import { AdminPageHeader } from '@/widgets/admin-layout'

const { me, name } = useSession()

const isAdmin = computed(() => me.value?.permissions.includes('admin') ?? false)

/** Права из токена — именно их проверяет бэкенд, пока токен не истёк */
const access = computed(() =>
  PERMISSION_GROUPS.map((group) => ({
    title: group.title,
    actions: group.items.filter((item) => isAdmin.value || me.value?.permissions.includes(item.permission)).map((item) => item.action),
    policies: me.value?.policies[group.items[0]!.permission] ?? [],
  })),
)
</script>

<template>
  <template v-if="me">
    <AdminPageHeader :title="name" :description="roleTitle(me.role.name)" />

    <div class="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <PanelCard title="Профиль">
        <ProfileForm :me="me" />
      </PanelCard>

      <div class="space-y-6">
        <PanelCard title="Вход">
          <dl class="space-y-3 text-sm">
            <div>
              <dt class="text-ink-secondary">Email</dt>
              <dd class="text-ink">{{ me.email ?? '—' }}</dd>
            </div>
            <div>
              <dt class="text-ink-secondary">Телефон</dt>
              <dd class="text-ink">{{ me.phone ?? '—' }}</dd>
            </div>
            <div>
              <dt class="text-ink-secondary">Сессия до</dt>
              <dd class="text-ink">{{ formatDateTime(new Date(session.state.expiresAt)) }}</dd>
            </div>
            <div>
              <dt class="text-ink-secondary">Источник данных</dt>
              <dd class="text-ink">{{ API_MODE === 'real' ? 'Identity API бэкенда' : 'демо-данные в браузере' }}</dd>
            </div>
          </dl>
        </PanelCard>

        <PanelCard title="Мои права">
          <p v-if="isAdmin" class="mb-3 text-sm text-brand">Полный доступ ко всем разделам</p>
          <ul class="space-y-3 text-sm">
            <li v-for="group in access" :key="group.title">
              <p class="font-medium text-ink">{{ group.title }}</p>
              <p class="mt-1 flex flex-wrap gap-1.5">
                <BaseBadge v-for="action in group.actions" :key="action" tone="success">{{ action }}</BaseBadge>
                <BaseBadge v-for="policy in group.policies" :key="policy" tone="warning">{{ POLICY_META[policy].label }}</BaseBadge>
                <span v-if="!group.actions.length" class="text-ink-muted">нет доступа</span>
              </p>
            </li>
          </ul>
        </PanelCard>
      </div>
    </div>
  </template>
</template>
