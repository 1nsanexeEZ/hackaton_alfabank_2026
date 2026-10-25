<script setup lang="ts">
import { AdminPageHeader } from '@/widgets/admin-layout'
import { ScoringOverview } from '@/widgets/scoring-overview'
</script>

<template>
  <AdminPageHeader
    title="Скоринг"
    description="Как PD- и ML-модель оценили поданные заявки: грейды, зоны и согласие моделей, полнота данных и решение"
  />
  <ScoringOverview />
</template>
