<script setup lang="ts">
import { DatabaseBackup } from 'lucide-vue-next'
import { ref } from 'vue'

import { useSession } from '@/entities/session'
import { ScoringConfigEditor } from '@/features/edit-scoring'
import { creditApi, type ScoringConfig } from '@/shared/api'
import { errorMessage, useAsyncData } from '@/shared/lib'
import { AsyncState, BaseButton, BaseModal } from '@/shared/ui'
import { AdminPageHeader, DemoSectionNote } from '@/widgets/admin-layout'

const { can } = useSession()

const config = useAsyncData(() => creditApi.getScoringConfig())

function onSaved(saved: ScoringConfig) {
  config.data.value = saved
}

const isResetOpen = ref(false)
const resetPending = ref(false)
const resetError = ref<string | null>(null)

async function resetDemo() {
  resetPending.value = true
  resetError.value = null
  try {
    await creditApi.resetDemoData()
    isResetOpen.value = false
    await config.reload()
  } catch (caught) {
    resetError.value = errorMessage(caught)
  } finally {
    resetPending.value = false
  }
}
</script>

<template>
  <AdminPageHeader
    title="Скоринг"
    description="Объяснимая балльная модель: веса факторов, стоп-факторы и пороги решения. Новые настройки применяются к следующему расчёту"
  >
    <template v-if="can('admin')" #actions>
      <BaseButton variant="secondary" size="s" @click="isResetOpen = true">
        <DatabaseBackup class="size-4" aria-hidden="true" />
        Сбросить демо-данные
      </BaseButton>
    </template>
  </AdminPageHeader>
  <DemoSectionNote text="Политика скоринга на бэкенде задана конфигом (scorecard_v1.yaml, policy_v1.yaml) и через API не меняется — настройки здесь работают только на синтетических заявках в браузере." />

  <AsyncState :loading="config.loading.value" :error="config.error.value" @retry="config.reload">
    <ScoringConfigEditor v-if="config.data.value" :config="config.data.value" :readonly="!can('admin')" @saved="onSaved" />
  </AsyncState>

  <BaseModal v-model:open="isResetOpen" title="Сбросить демо-данные?">
    <p class="text-sm text-ink">
      Заявки, решения, условия продуктов и настройки скоринга вернутся к исходным. Пользователи и роли не изменятся.
    </p>
    <p v-if="resetError" class="mt-3 text-sm text-brand" role="alert">{{ resetError }}</p>
    <template #footer>
      <BaseButton variant="secondary" @click="isResetOpen = false">Отмена</BaseButton>
      <BaseButton :loading="resetPending" @click="resetDemo">Сбросить</BaseButton>
    </template>
  </BaseModal>
</template>
