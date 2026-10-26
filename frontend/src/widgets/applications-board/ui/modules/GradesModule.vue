<script setup lang="ts">
import { computed, onMounted } from 'vue'

import { GRADE_ZONE } from '@/entities/underwriting'
import { BarList } from '@/shared/ui'

import { useBoard } from '../../model/useBoardData'

const { scoring, scoringLoading, loadScoring } = useBoard()

// Сводка скоринга нужна только этому модулю: грузим, когда он на панели
onMounted(() => void loadScoring())

const ZONE_COLOR = { green: 'var(--color-success)', yellow: 'var(--color-signal-warn)', red: 'var(--color-brand)' } as const

/** Грейды PD-модели, которые встретились, — по порядку A…J; считает бэкенд по последним поданным */
const items = computed(() =>
  (scoring.value?.by_grade ?? [])
    .filter((row) => row.pd > 0)
    .map((row) => ({ label: `Грейд ${row.grade}`, value: row.pd, color: ZONE_COLOR[GRADE_ZONE[row.grade]] })),
)

/** Средний балл — по последним поданным заявкам, у которых он есть */
const average = computed(() => {
  const scores = (scoring.value?.items ?? []).map((item) => item.score).filter((score): score is number => score !== null)
  return scores.length ? { value: Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length), count: scores.length } : null
})
</script>

<template>
  <div>
    <p v-if="average" class="mb-4 text-sm text-ink-secondary">
      Средний балл <b class="font-semibold text-ink">{{ average.value }}</b> по {{ average.count }} последним заявкам
    </p>
    <BarList v-if="items.length" :items="items" />
    <p v-else class="text-sm text-ink-secondary">{{ scoringLoading ? 'Собираем оценки…' : 'Оценённых заявок пока нет' }}</p>
  </div>
</template>
