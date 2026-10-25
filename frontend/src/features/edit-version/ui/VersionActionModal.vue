<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { VERSION_KIND_META, versionsApi, type VersionKind } from '@/entities/scoring-version'
import type { VersionDto, VersionSummaryDto } from '@/shared/api'
import { errorMessage } from '@/shared/lib'
import { BaseButton, BaseModal } from '@/shared/ui'

/**
 * activate — черновик или архивная версия становится действующей (это и откат), прежняя уходит в
 * архив; у встроенной — вернуть YAML. delete — удалить черновик (204)
 */
const props = defineProps<{ kind: VersionKind; version: VersionSummaryDto | null; action: 'activate' | 'delete' }>()
const open = defineModel<boolean>('open', { required: true })
const emit = defineEmits<{ activated: [version: VersionDto]; deleted: [version: string] }>()

const pending = ref(false)
const error = ref<string | null>(null)
watch(open, (isOpen) => {
  if (isOpen) error.value = null
})

const text = computed(() => {
  const what = VERSION_KIND_META[props.kind].title
  if (props.action === 'delete') {
    return { title: 'Удалить черновик?', body: 'Черновик удалится насовсем. Действующая версия не изменится.', button: 'Удалить' }
  }
  if (props.version?.builtin) {
    return {
      title: 'Вернуть встроенную версию?',
      body: `${what} снова будет считаться по YAML из кода, действующая версия админа уйдёт в архив.`,
      button: 'Вернуть встроенную',
    }
  }
  return {
    title: props.version?.status === 'archived' ? 'Откатиться на эту версию?' : 'Активировать версию?',
    body: `${what} этой версии будет считать заявки со следующей команды; прежние результаты останутся на своей версии. Действующая сейчас уйдёт в архив.`,
    button: 'Активировать',
  }
})

async function confirm() {
  if (!props.version) return
  pending.value = true
  error.value = null
  try {
    const api = versionsApi(props.kind)
    if (props.action === 'delete') {
      await api.deleteDraft(props.version.version)
      emit('deleted', props.version.version)
    } else {
      emit('activated', await api.activate(props.version.version))
    }
    open.value = false
  } catch (caught) {
    error.value = errorMessage(caught)
  } finally {
    pending.value = false
  }
}
</script>

<template>
  <BaseModal v-model:open="open" :title="text.title">
    <p class="text-sm text-ink">
      <b class="font-semibold">{{ version?.version }}</b
      ><template v-if="version?.comment"> · {{ version.comment }}</template>
    </p>
    <p class="mt-2 text-sm text-ink-secondary">{{ text.body }}</p>
    <p v-if="error" class="mt-3 text-sm text-brand" role="alert">{{ error }}</p>
    <template #footer>
      <BaseButton variant="secondary" @click="open = false">Отмена</BaseButton>
      <BaseButton :loading="pending" @click="confirm">{{ text.button }}</BaseButton>
    </template>
  </BaseModal>
</template>
