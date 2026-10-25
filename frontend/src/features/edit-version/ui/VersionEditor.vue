<script setup lang="ts">
import { AlertCircle, Save, Undo2 } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

import { bodyErrors, versionsApi, type VersionKind } from '@/entities/scoring-version'
import type { ModelCatalogDto, PolicyCatalogDto, VersionBody, VersionBodyError, VersionDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'
import { BaseButton, SegmentedControl, TextField } from '@/shared/ui'

import ModelKeyFields from './ModelKeyFields.vue'
import PolicyKeyFields from './PolicyKeyFields.vue'

/**
 * Документ версии: ключевые поля формой, остальное — JSON целиком. Обе вкладки правят один документ.
 * Сохраняется документ целиком (PUT); бэкенд проверяет его так же, как YAML, и все ошибки
 * возвращает списком { path, message } — подсвечиваем поля и показываем список.
 */
const props = defineProps<{
  kind: VersionKind
  version: VersionDto
  catalog: ModelCatalogDto | PolicyCatalogDto | null
  /** Черновик и есть scoring.update */
  editable: boolean
}>()
const emit = defineEmits<{ saved: [version: VersionDto] }>()

type Tab = 'fields' | 'json'
const TABS: { value: Tab; label: string }[] = [
  { value: 'fields', label: 'Основное' },
  { value: 'json', label: 'Документ целиком (JSON)' },
]
const tab = ref<Tab>('fields')

const body = ref<VersionBody>({})
const original = ref('')
const comment = ref('')
const jsonText = ref('')
const jsonError = ref<string | null>(null)
const errors = ref<VersionBodyError[]>([])
const saveError = ref<string | null>(null)
const pending = ref(false)

function reset() {
  body.value = structuredClone(props.version.body)
  original.value = JSON.stringify(props.version.body)
  comment.value = props.version.comment ?? ''
  jsonError.value = null
  errors.value = []
  saveError.value = null
  if (tab.value === 'json') jsonText.value = JSON.stringify(body.value, null, 2)
}
watch(() => props.version, reset, { immediate: true })

watch(tab, (next) => {
  if (next === 'json') jsonText.value = JSON.stringify(body.value, null, 2)
})

function onJson(text: string) {
  jsonText.value = text
  try {
    const parsed: unknown = JSON.parse(text)
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Документ — объект { … }')
    body.value = parsed as VersionBody
    jsonError.value = null
  } catch (caught) {
    jsonError.value = `JSON не разобран: ${errorMessage(caught)}`
  }
}

const modelCatalog = computed(() => (props.kind === 'model' ? (props.catalog as ModelCatalogDto | null) : null))
const policyCatalog = computed(() => (props.kind === 'policy' ? (props.catalog as PolicyCatalogDto | null) : null))

const dirty = computed(() => JSON.stringify(body.value) !== original.value || comment.value !== (props.version.comment ?? ''))
const errorMap = computed(() => Object.fromEntries(errors.value.map((item) => [item.path, item.message])))

async function save() {
  if (jsonError.value) return
  pending.value = true
  errors.value = []
  saveError.value = null
  try {
    const saved = await versionsApi(props.kind).updateDraft(props.version.version, {
      body: body.value,
      comment: comment.value.trim() || undefined,
    })
    emit('saved', saved)
  } catch (caught) {
    errors.value = bodyErrors(caught)
    saveError.value = errors.value.length ? 'Документ не прошёл проверку' : errorMessage(caught)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <div class="space-y-5">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <SegmentedControl v-model="tab" :options="TABS" label="Как показать документ" small />
      <p v-if="!editable" class="text-xs text-ink-secondary">
        {{ version.status === 'draft' ? 'Правка черновиков — с правом scoring.update' : 'Править можно только черновик — скопируйте версию' }}
      </p>
    </div>

    <div v-if="saveError" class="rounded-xl bg-brand-soft p-4 text-sm text-brand" role="alert">
      <p class="flex items-center gap-2 font-semibold"><AlertCircle class="size-4" aria-hidden="true" />{{ saveError }}</p>
      <ul v-if="errors.length" class="mt-2 space-y-1 text-ink">
        <li v-for="item in errors" :key="`${item.path}-${item.message}`">
          <code class="text-xs text-brand">{{ item.path || 'документ' }}</code> — {{ item.message }}
        </li>
      </ul>
    </div>

    <template v-if="tab === 'fields'">
      <ModelKeyFields v-if="kind === 'model'" :body="body" :catalog="modelCatalog" :errors="errorMap" :readonly="!editable" />
      <PolicyKeyFields v-else :body="body" :catalog="policyCatalog" :errors="errorMap" :readonly="!editable" />
    </template>
    <div v-else>
      <label for="version-json" class="sr-only">Документ версии в JSON</label>
      <textarea
        id="version-json"
        :value="jsonText"
        :readonly="!editable"
        spellcheck="false"
        class="h-[60vh] w-full rounded-xl bg-surface p-4 font-mono text-xs leading-relaxed text-ink outline-none focus:bg-white focus:ring-2 focus:ring-ink/20"
        :class="jsonError && 'ring-1 ring-brand'"
        @input="onJson(($event.target as HTMLTextAreaElement).value)"
      />
      <p v-if="jsonError" class="mt-1 text-sm text-brand" role="alert">{{ jsonError }}</p>
      <p v-else class="mt-1 text-xs text-ink-secondary">Decimal — строками, как в YAML; поле version бэкенд заменит кодом версии</p>
    </div>

    <div v-if="editable" class="flex flex-wrap items-end gap-3 border-t border-line pt-4">
      <TextField v-model="comment" class="min-w-56 flex-1" label="Комментарий к версии" placeholder="Что поменяли и зачем" dense :maxlength="500" />
      <BaseButton variant="ghost" :disabled="!dirty || pending" @click="reset">
        <Undo2 class="size-4" aria-hidden="true" />
        Отменить правки
      </BaseButton>
      <BaseButton :loading="pending" :disabled="!dirty || Boolean(jsonError)" @click="save">
        <Save class="size-4" aria-hidden="true" />
        Сохранить черновик
      </BaseButton>
    </div>
  </div>
</template>
