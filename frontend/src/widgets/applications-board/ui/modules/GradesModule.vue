<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'

import { GRADE_ZONE } from '@/entities/underwriting'
import type { Grade } from '@/shared/api'
import { BarList } from '@/shared/ui'

import { useBoard } from '../../model/useBoardData'

const { cards, cardsLoading, loadCards, applications, applicationsLoading } = useBoard()

// Карточки нужны только этому модулю: грузим, когда он на панели и список заявок уже есть
onMounted(() => {
  if (!applicationsLoading.value) void loadCards()
})
watch(applicationsLoading, (loading) => !loading && applications.value.length && void loadCards())

const ZONE_COLOR = { green: 'var(--color-success)', yellow: 'var(--color-signal-warn)', red: 'var(--color-brand)' } as const

const scored = computed(() => cards.value.filter((card) => card.scoring))

/** Только грейды, которые встретились, — по порядку A…J */
const items = computed(() => {
  const counts = new Map<Grade, number>()
  for (const card of scored.value) counts.set(card.scoring!.grade, (counts.get(card.scoring!.grade) ?? 0) + 1)
  return (Object.keys(GRADE_ZONE) as Grade[])
    .filter((grade) => counts.has(grade))
    .map((grade) => ({ label: `Грейд ${grade}`, value: counts.get(grade)!, color: ZONE_COLOR[GRADE_ZONE[grade]] }))
})

const averageScore = computed(() =>
  scored.value.length ? Math.round(scored.value.reduce((sum, card) => sum + card.scoring!.score, 0) / scored.value.length) : null,
)
</script>

<template>
  <div>
    <p v-if="averageScore !== null" class="mb-4 text-sm text-ink-secondary">
      Средний балл <b class="font-semibold text-ink">{{ averageScore }}</b> по {{ scored.length }} заявкам
    </p>
    <BarList v-if="items.length" :items="items" />
    <p v-else class="text-sm text-ink-secondary">{{ cardsLoading ? 'Собираем оценки…' : 'Оценённых заявок пока нет' }}</p>
  </div>
</template>
