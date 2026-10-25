<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { VERSION_KIND_META, VERSION_STATUS_META, versionsApi, type VersionKind } from '@/entities/scoring-version'
import type { VersionDto, VersionSummaryDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'
import { BaseButton, BaseModal, SelectField, TextField } from '@/shared/ui'

/** Черновик — копия любой версии, в том числе встроенной или архивной (POST, 201) */
const props = defineProps<{
  kind: VersionKind
  versions: readonly VersionSummaryDto[]
  /** С какой версии копировать по умолчанию; иначе — действующая */
  basedOn?: string | null
}>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ created: [version: VersionDto] }>()

const source = ref('')
const comment = ref('')
const pending = ref(false)
const error = ref<string | null>(null)

watch(open, (isOpen) => {
  if (!isOpen) return
  source.value = props.basedOn ?? props.versions.find((item) => item.status === 'active')?.version ?? props.versions[0]?.version ?? ''
  comment.value = ''
  error.value = null
})

const options = computed(() =>
  props.versions.map((item) => ({
    value: item.version,
    label: `${item.version} · ${VERSION_STATUS_META[item.status].label.toLowerCase()}${item.builtin ? ', встроенная' : ''}`,
  })),
)

async function create() {
  if (!source.value) return
  pending.value = true
  error.value = null
  try {
    const created = await versionsApi(props.kind).createDraft({ based_on: source.value, comment: comment.value.trim() || undefined })
    emit('created', created)
    open.value = false
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <BaseModal v-model:open="open" :title="`Новый черновик: ${VERSION_KIND_META[kind].title}`" description="Черновик ни на что не влияет, пока его не активировать">
    <form id="draft-form" class="space-y-4" @submit.prevent="create">
      <SelectField v-model="source" label="Скопировать версию" :options="options" dense />
      <TextField v-model="comment" label="Комментарий" placeholder="Например: строже к долговой нагрузке" dense :maxlength="500" />
    </form>
    <p v-if="error" class="mt-3 text-sm text-brand" role="alert">{{ error }}</p>
    <template #footer>
      <BaseButton variant="secondary" @click="open = false">Отмена</BaseButton>
      <BaseButton type="submit" form="draft-form" :loading="pending" :disabled="!source">Создать черновик</BaseButton>
    </template>
  </BaseModal>
</template>
