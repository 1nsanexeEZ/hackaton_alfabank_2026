<script setup lang="ts">
import { Copy, Pencil, Rocket, Trash2, Undo2 } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { VERSION_KIND_META, VERSION_STATUS_META, versionsApi, type VersionKind } from '@/entities/scoring-version'
import { displayName, useSession } from '@/entities/session'
import { CreateDraftModal, draftToEdit, VersionActionModal, VersionEditor } from '@/features/edit-version'
import { backofficeApi, identityApi, type ModelCatalogDto, type PolicyCatalogDto, type VersionDto } from '@/shared/api'
import { ADMIN_ROUTE } from '@/shared/config'
import { errorMessage, formatDateTime, useAsyncData } from '@/shared/lib'
import { AsyncState, BaseBadge, BaseButton, PanelCard, SegmentedControl } from '@/shared/ui'
import { AdminPageHeader } from '@/widgets/admin-layout'
import { VersionPreview } from '@/widgets/version-preview'

import VersionCatalog from './VersionCatalog.vue'

/** Версия PD-модели или кредитной политики: документ, примерка на прошлых заявках, справочник */
const props = defineProps<{ kind: VersionKind; version: string }>()

const router = useRouter()
const { can } = useSession()

const version = useAsyncData(() => versionsApi(props.kind).get(props.version))
const versions = useAsyncData(() => versionsApi(props.kind).list())
// Переход на копию или основу — та же страница с другими параметрами: перечитываем
watch(
  () => [props.kind, props.version],
  () => {
    void version.reload()
    void versions.reload()
  },
)
const catalog = useAsyncData<ModelCatalogDto | PolicyCatalogDto>(() =>
  props.kind === 'model' ? backofficeApi.scoringModels.catalog() : backofficeApi.decisionPolicies.catalog(),
)
/** Кто создал и активировал — по id сотрудника, если можно читать пользователей */
const accounts = useAsyncData(() => (can('accounts.read') ? identityApi.listAllAccounts() : Promise.resolve([])))
const who = (id: string | null) => {
  if (!id) return null
  const account = accounts.data.value?.find((item) => item.id === id)
  return account ? displayName(account) : null
}

type Tab = 'document' | 'preview' | 'catalog'
const TABS: { value: Tab; label: string }[] = [
  { value: 'document', label: 'Документ' },
  { value: 'preview', label: 'Примерка' },
  { value: 'catalog', label: 'Справочник' },
]
const tab = ref<Tab>('document')

const canManage = computed(() => can('scoring.update'))
const current = computed(() => version.data.value)
const editable = computed(() => canManage.value && current.value?.status === 'draft')
/** Черновик и архивная — активировать (откат); встроенная, пока не действует, — вернуть YAML */
const canActivate = computed(
  () => canManage.value && current.value && current.value.status !== 'active' && (current.value.status === 'draft' || current.value.status === 'archived'),
)

const action = ref<'activate' | 'delete'>('activate')
const isActionOpen = ref(false)
const isCopyOpen = ref(false)

function ask(next: 'activate' | 'delete') {
  action.value = next
  isActionOpen.value = true
}

function onChanged(saved: VersionDto) {
  version.data.value = saved
  void versions.reload()
}

const list = { name: ADMIN_ROUTE.versions, query: { kind: props.kind } }
const openCopy = (created: VersionDto) =>
  router.push({ name: ADMIN_ROUTE.version, params: { kind: props.kind, version: created.version } })

/** «Изменить» действующую или архивную: открываем черновик на её основе — он сразу правится */
const editing = ref(false)
const editError = ref<string | null>(null)

async function edit() {
  if (!current.value) return
  editing.value = true
  editError.value = null
  try {
    const draft = await draftToEdit(props.kind, current.value.version, versions.data.value ?? [])
    await router.push({ name: ADMIN_ROUTE.version, params: { kind: props.kind, version: draft } })
  } catch (caught) {
    editError.value = errorMessage(caught)
  } finally {
    editing.value = false
  }
}
</script>

<template>
  <AdminPageHeader :title="current?.version ?? props.version" :back="list" :back-label="VERSION_KIND_META[kind].title">
    <template #meta>
      <p class="mt-2 flex flex-wrap items-center gap-2 text-sm text-ink-secondary">
        <span>{{ VERSION_KIND_META[kind].title }}</span>
        <BaseBadge v-if="current" :tone="VERSION_STATUS_META[current.status].tone">{{ VERSION_STATUS_META[current.status].label }}</BaseBadge>
        <BaseBadge v-if="current?.builtin">встроенная</BaseBadge>
      </p>
    </template>
    <template v-if="current && canManage" #actions>
      <BaseButton
        v-if="current.status !== 'draft'"
        size="s"
        :variant="current.status === 'active' ? 'primary' : 'secondary'"
        :loading="editing"
        :disabled="!versions.data.value"
        @click="edit"
      >
        <Pencil class="size-4" aria-hidden="true" />
        Изменить
      </BaseButton>
      <BaseButton v-else size="s" variant="secondary" :disabled="!versions.data.value" @click="isCopyOpen = true">
        <Copy class="size-4" aria-hidden="true" />
        Копировать в черновик
      </BaseButton>
      <BaseButton v-if="canActivate" size="s" @click="ask('activate')">
        <component :is="current.builtin || current.status === 'archived' ? Undo2 : Rocket" class="size-4" aria-hidden="true" />
        {{ current.builtin ? 'Вернуть встроенную' : current.status === 'archived' ? 'Откатиться на неё' : 'Активировать' }}
      </BaseButton>
      <BaseButton v-if="current.status === 'draft'" size="s" variant="ghost" @click="ask('delete')">
        <Trash2 class="size-4" aria-hidden="true" />
        Удалить черновик
      </BaseButton>
    </template>
  </AdminPageHeader>

  <AsyncState :loading="version.loading.value" :error="version.error.value" :empty="!current" @retry="version.reload">
    <template v-if="current">
      <p v-if="editError" class="mb-4 rounded-xl bg-brand-soft px-4 py-3 text-sm text-brand" role="alert">{{ editError }}</p>
      <p v-if="current.status === 'draft' && canManage" class="mb-4 rounded-xl bg-warning-soft px-4 py-3 text-sm text-ink">
        Черновик ни на что не влияет: поправьте документ, сохраните и нажмите «Активировать» — с этого момента по нему
        считаются новые заявки
      </p>
      <dl class="mb-6 grid gap-x-6 gap-y-3 rounded-2xl bg-white p-5 text-sm ring-1 ring-line sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt class="text-ink-secondary">На основе</dt>
          <dd class="text-ink">
            <RouterLink v-if="current.based_on" :to="{ name: ADMIN_ROUTE.version, params: { kind, version: current.based_on } }" class="hover:text-brand">
              {{ current.based_on }}
            </RouterLink>
            <template v-else>{{ current.builtin ? 'YAML в коде' : '—' }}</template>
          </dd>
        </div>
        <div>
          <dt class="text-ink-secondary">Создана</dt>
          <dd class="text-ink">
            {{ current.created_at ? formatDateTime(current.created_at) : '—' }}
            <span v-if="who(current.created_by)" class="block text-xs text-ink-secondary">{{ who(current.created_by) }}</span>
          </dd>
        </div>
        <div>
          <dt class="text-ink-secondary">Изменена</dt>
          <dd class="text-ink">{{ current.updated_at ? formatDateTime(current.updated_at) : '—' }}</dd>
        </div>
        <div>
          <dt class="text-ink-secondary">Активирована</dt>
          <dd class="text-ink">
            {{ current.activated_at ? formatDateTime(current.activated_at) : '—' }}
            <span v-if="who(current.activated_by)" class="block text-xs text-ink-secondary">{{ who(current.activated_by) }}</span>
          </dd>
        </div>
        <div v-if="current.comment" class="sm:col-span-2 lg:col-span-4">
          <dt class="text-ink-secondary">Комментарий</dt>
          <dd class="text-ink">{{ current.comment }}</dd>
        </div>
      </dl>

      <SegmentedControl v-model="tab" :options="TABS" label="Раздел версии" class="mb-4" />

      <PanelCard v-show="tab === 'document'">
        <VersionEditor :kind="kind" :version="current" :catalog="catalog.data.value" :editable="editable" @saved="onChanged" />
      </PanelCard>
      <PanelCard v-if="tab === 'preview'">
        <VersionPreview :kind="kind" :version="current.version" />
      </PanelCard>
      <PanelCard v-if="tab === 'catalog'">
        <AsyncState :loading="catalog.loading.value" :error="catalog.error.value" :empty="!catalog.data.value" @retry="catalog.reload">
          <VersionCatalog v-if="catalog.data.value" :kind="kind" :catalog="catalog.data.value" />
        </AsyncState>
      </PanelCard>
    </template>
  </AsyncState>

  <VersionActionModal
    v-model:open="isActionOpen"
    :kind="kind"
    :version="current ?? null"
    :action="action"
    @activated="onChanged"
    @deleted="router.push(list)"
  />
  <CreateDraftModal v-model:open="isCopyOpen" :kind="kind" :versions="versions.data.value ?? []" :based-on="current?.version" @created="openCopy" />
</template>
