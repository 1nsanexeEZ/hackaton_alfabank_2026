<script setup lang="ts">
import { SearchX } from 'lucide-vue-next'
import { shallowRef } from 'vue'

import { ScoreBreakdown } from '@/entities/application'
import { InnLookupForm } from '@/features/check-inn'
import type { Dossier, ScoreResult } from '@/shared/api'
import { PanelCard } from '@/shared/ui'
import { AdminPageHeader } from '@/widgets/admin-layout'
import { CounterpartyDossier } from '@/widgets/counterparty-dossier'

const result = shallowRef<{ dossier: Dossier; score: ScoreResult } | null>(null)
const notFoundInn = shallowRef<string | null>(null)

function onResult(value: { dossier: Dossier; score: ScoreResult } | null, inn: string) {
  result.value = value
  notFoundInn.value = value ? null : inn
}
</script>

<template>
  <AdminPageHeader
    title="Проверка по ИНН"
    description="Досье из ЕГРЮЛ/ЕГРИП, ФНС, ГИР БО и Контура и предварительный скоринг — до того, как клиент подал заявку"
  />

  <PanelCard>
    <InnLookupForm @result="onResult" />
  </PanelCard>

  <PanelCard v-if="notFoundInn" class="mt-6">
    <div class="flex items-start gap-3">
      <SearchX class="size-6 shrink-0 text-ink-muted" aria-hidden="true" />
      <div>
        <p class="font-semibold text-ink">ИНН {{ notFoundInn }} не найден</p>
        <p class="mt-1 text-sm text-ink-secondary">Ни один источник не вернул данных. Проверьте номер или запросите документы у клиента.</p>
      </div>
    </div>
  </PanelCard>

  <div v-if="result" class="mt-6 space-y-6">
    <PanelCard title="Предварительный скоринг" description="Расчёт по текущим настройкам скоринга, без сохранения">
      <ScoreBreakdown :score="result.score" />
    </PanelCard>
    <CounterpartyDossier :dossier="result.dossier" />
  </div>
</template>
