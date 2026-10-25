<script setup lang="ts">
import { Plus } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  isVersionKind,
  VERSION_KIND_META,
  VERSION_KINDS,
  VERSION_STATUS_META,
  versionsApi,
  type VersionKind,
} from '@/entities/scoring-version'
import { useSession } from '@/entities/session'
import { CreateDraftModal } from '@/features/edit-version'
import type { VersionDto } from '@/shared/api'
import { ADMIN_ROUTE } from '@/shared/config'
import { formatDateTime, useAsyncData } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton, PanelCard, SegmentedControl } from '@/shared/ui'
import { AdminPageHeader } from '@/widgets/admin-layout'

/**
 * Версии PD-модели и кредитной политики (/scoring/models, /decision/policies): какая действует,
 * черновики и архив. Читать и примерять — scoring.read, вести — scoring.update
 */
const route = useRoute()
const router = useRouter()
const { can } = useSession()

const kind = computed<VersionKind>(() => (isVersionKind(route.query.kind) ? route.query.kind : 'model'))
const KIND_OPTIONS = VERSION_KINDS.map((value) => ({ value, label: VERSION_KIND_META[value].title }))
const selected = computed({
  get: () => kind.value,
  set: (value: VersionKind) => void router.replace({ query: { ...route.query, kind: value } }),
})

const versions = useAsyncData(() => versionsApi(kind.value).list())
watch(kind, () => void versions.reload())

const active = computed(() => versions.data.value?.find((item) => item.status === 'active') ?? null)

const isCreateOpen = ref(false)
const openVersion = (version: VersionDto | string) =>
  router.push({
    name: ADMIN_ROUTE.version,
    params: { kind: kind.value, version: typeof version === 'string' ? version : version.version },
  })
</script>

<template>
  <AdminPageHeader title="Модель и политика" description="Версии PD-модели и кредитной политики: черновик, примерка на прошлых заявках, активация и откат">
    <template v-if="can('scoring.update')" #actions>
      <BaseButton size="s" :disabled="!versions.data.value" @click="isCreateOpen = true">
        <Plus class="size-4" aria-hidden="true" />
        Новый черновик
      </BaseButton>
    </template>
  </AdminPageHeader>

  <SegmentedControl v-model="selected" :options="KIND_OPTIONS" label="Чьи версии показать" class="mb-4" />
  <p class="mb-4 text-sm text-ink-secondary">{{ VERSION_KIND_META[kind].description }}</p>

  <AsyncState :loading="versions.loading.value" :error="versions.error.value" :empty="!versions.data.value?.length" @retry="versions.reload">
    <p v-if="active" class="mb-4 rounded-xl bg-success-soft px-4 py-3 text-sm text-ink">
      Сейчас действует <b class="font-semibold">{{ active.version }}</b
      >{{ active.builtin ? ' — встроенная, из YAML в коде' : active.activated_at ? `, с ${formatDateTime(active.activated_at)}` : '' }}
    </p>

    <PanelCard flush>
      <div class="overflow-x-auto">
        <table class="w-full min-w-[44rem] text-sm">
          <thead class="text-xs text-ink-secondary">
            <tr class="border-b border-line">
              <th scope="col" class="px-5 py-3 text-left font-medium">Версия</th>
              <th scope="col" class="px-3 py-3 text-left font-medium">Статус</th>
              <th scope="col" class="px-3 py-3 text-left font-medium">На основе</th>
              <th scope="col" class="px-3 py-3 text-left font-medium">Комментарий</th>
              <th scope="col" class="px-3 py-3 text-left font-medium">Изменена</th>
              <th scope="col" class="px-5 py-3 text-left font-medium">Активирована</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in versions.data.value"
              :key="item.version"
              class="cursor-pointer border-b border-line last:border-0 hover:bg-surface-soft"
              @click="openVersion(item.version)"
            >
              <td class="px-5 py-3">
                <RouterLink
                  :to="{ name: ADMIN_ROUTE.version, params: { kind, version: item.version } }"
                  class="font-semibold text-ink hover:text-brand"
                  @click.stop
                >
                  {{ item.version }}
                </RouterLink>
                <p v-if="item.builtin" class="text-xs text-ink-muted">встроенная, только чтение</p>
              </td>
              <td class="px-3 py-3"><BaseBadge :tone="VERSION_STATUS_META[item.status].tone">{{ VERSION_STATUS_META[item.status].label }}</BaseBadge></td>
              <td class="px-3 py-3 text-ink-secondary">{{ item.based_on ?? '—' }}</td>
              <td class="max-w-xs px-3 py-3 text-ink-secondary">{{ item.comment ?? '—' }}</td>
              <td class="px-3 py-3 whitespace-nowrap text-ink-secondary">{{ item.updated_at ? formatDateTime(item.updated_at) : '—' }}</td>
              <td class="px-5 py-3 whitespace-nowrap text-ink-secondary">{{ item.activated_at ? formatDateTime(item.activated_at) : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </PanelCard>
  </AsyncState>

  <CreateDraftModal v-model:open="isCreateOpen" :kind="kind" :versions="versions.data.value ?? []" @created="openVersion" />
</template>
